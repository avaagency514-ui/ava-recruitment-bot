"""
ava-recruitment-bot
Bot Telegram de publication d'annonces de recrutement.
- Génère 3-5 annonces variées au démarrage via Gemini API (fallback: Groq)
- Les publie en rotation dans les groupes Telegram configurés
- Publie toutes les heures (heure pile)
- Reconnexion automatique infinie (Railway 24/7)
"""

import os
import sys
import json
import asyncio
import logging
import random
from datetime import datetime, timedelta

import requests
from telegram import Bot
from telegram.error import TelegramError
from telegram.constants import ParseMode

# ─── Logging vers stdout (Railway) ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("RecruitBot")

# ─── Configuration depuis variables d'environnement ───────────────────────────
BOT_TOKEN      = os.environ.get("TELEGRAM_TOKEN", "")
TARGET_GROUPS  = [g.strip() for g in os.environ.get("TARGET_GROUPS", "").split(",") if g.strip()]
POST_INTERVAL  = int(os.environ.get("POST_INTERVAL", "3600"))   # secondes (défaut 1h)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
NB_ANNONCES    = int(os.environ.get("NB_ANNONCES", "5"))         # 3 à 5 annonces générées

# ─── Annonces de base (fallback si IA indisponible) ──────────────────────────
ANNONCES_FALLBACK = [
    (
        "🚀 RECRUTEMENT — VA INSTAGRAM (Mobile / iPhone)\n\n"
        "🎯 Mission :\n"
        "• Créer des comptes Instagram (méthode fournie)\n"
        "• Poster des Reels & stories (contenu fourni)\n"
        "• 1 à 3h/jour — travail flexible mais QUOTIDIEN\n\n"
        "💰 Paiement 2x/mois (Crypto ou TapTap Send)\n"
        "🔥 Commission si tu ramènes des VA qui rejoignent l'agence\n\n"
        "📩 DM maintenant si tu es intéressé(e) !"
    ),
    (
        "🚀 RECRUTEMENT — OPÉRATEUR INSTAGRAM (PC)\n\n"
        "🎯 Mission :\n"
        "• Configuration d'environnements mobiles sur PC\n"
        "• Créer des comptes Instagram & poster du contenu\n"
        "• 1 à 3h/jour — flexible mais QUOTIDIEN\n\n"
        "💰 Paiement 2x/mois | Potentiel élevé\n"
        "🔥 Bonus parrainage si tu recrutes des VA\n\n"
        "📩 DM maintenant si tu es intéressé(e) !"
    ),
]

# ─── Génération d'annonces via Gemini API ─────────────────────────────────────
def generate_via_gemini(prompt: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 600}
        }
        res = requests.post(url, json=body, timeout=20)
        if res.status_code == 200:
            data = res.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            log.info("✅ Annonce générée via Gemini")
            return text
        else:
            log.warning(f"⚠️ Gemini HTTP {res.status_code}: {res.text[:100]}")
    except Exception as e:
        log.warning(f"⚠️ Erreur Gemini : {e}")
    return None

# ─── Génération d'annonces via Groq (fallback) ───────────────────────────────
def generate_via_groq(prompt: str) -> str | None:
    if not GROQ_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "max_tokens": 600
            },
            timeout=20
        )
        if res.status_code == 200:
            text = res.json()["choices"][0]["message"]["content"].strip()
            log.info("✅ Annonce générée via Groq (fallback)")
            return text
        else:
            log.warning(f"⚠️ Groq HTTP {res.status_code}: {res.text[:100]}")
    except Exception as e:
        log.warning(f"⚠️ Erreur Groq : {e}")
    return None

# ─── Génération avec Gemini → Groq → fallback statique ───────────────────────
def generate_annonce(index: int) -> str:
    styles = [
        "urgente et percutante, en utilisant des emojis dynamiques",
        "professionnelle et détaillée, avec bullet points clairs",
        "motivante et inspirante, qui donne envie de rejoindre l'équipe",
        "directe et concise, maximum 10 lignes, très impactante",
        "amicale et accessible, comme si tu parlais à un(e) ami(e)",
    ]
    style = styles[index % len(styles)]

    prompt = (
        f"Tu es expert en recrutement pour une agence digitale française. "
        f"Écris une annonce de recrutement pour des Virtual Assistants (VA) Telegram/Instagram, "
        f"dans un style {style}. "
        f"L'annonce doit inclure : le type de mission (créer et gérer des comptes Instagram/Telegram, "
        f"poster du contenu fourni), la rémunération (paiement 2x/mois en crypto ou TapTap Send, "
        f"à la performance), les exigences (smartphone ou PC, disponible quotidiennement 1-3h/jour), "
        f"et finir par 'DM maintenant si intéressé(e)'. "
        f"Maximum 20 lignes. Utilise des emojis. Écris UNIQUEMENT l'annonce, sans introduction ni commentaire."
    )

    text = generate_via_gemini(prompt) or generate_via_groq(prompt)
    if text:
        return text

    # Fallback statique
    log.warning(f"⚠️ IA indisponible pour annonce {index+1} — utilisation du texte de base")
    return ANNONCES_FALLBACK[index % len(ANNONCES_FALLBACK)]

# ─── Chargement des annonces au démarrage ────────────────────────────────────
def load_annonces() -> list[str]:
    log.info(f"🤖 Génération de {NB_ANNONCES} annonces via IA (Gemini → Groq → fallback)...")
    annonces = []
    for i in range(NB_ANNONCES):
        log.info(f"  → Génération annonce {i+1}/{NB_ANNONCES}...")
        annonce = generate_annonce(i)
        annonces.append(annonce)
        # Petite pause pour ne pas spammer l'API
        import time; time.sleep(1)
    log.info(f"✅ {len(annonces)} annonces prêtes pour la rotation.")
    return annonces

# ─── Publication dans les groupes ────────────────────────────────────────────
async def publish_annonces(bot: Bot, annonces: list[str], annonce_index: int) -> int:
    if not annonces:
        log.warning("⚠️ Aucune annonce disponible.")
        return annonce_index

    annonce = annonces[annonce_index % len(annonces)]
    horodatage = datetime.now().strftime("%d/%m/%Y %H:%M")
    ref = f"REF-{datetime.now().strftime('%Y%m%d%H%M')}"
    full_message = f"{annonce}\n\n—\n📅 Publié le {horodatage} | {ref}"

    log.info(f"📢 Publication annonce {(annonce_index % len(annonces)) + 1}/{len(annonces)} dans {len(TARGET_GROUPS)} groupe(s)...")

    for groupe in TARGET_GROUPS:
        try:
            await bot.send_message(
                chat_id=groupe,
                text=full_message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            log.info(f"  ✅ Envoyé dans {groupe}")
            await asyncio.sleep(2)
        except TelegramError as e:
            log.error(f"  ❌ Erreur dans {groupe}: {e}")

    return annonce_index + 1

# ─── Boucle principale ────────────────────────────────────────────────────────
async def main_loop():
    if not BOT_TOKEN:
        log.error("❌ TELEGRAM_TOKEN non défini ! Configurez la variable d'environnement Railway.")
        sys.exit(1)

    if not TARGET_GROUPS:
        log.error("❌ TARGET_GROUPS non défini ! Configurez les IDs des groupes (séparés par virgule).")
        sys.exit(1)

    log.info("=" * 50)
    log.info("🚀 AVA Agency — Bot Recrutement IA")
    log.info(f"   Groupes cibles : {len(TARGET_GROUPS)}")
    log.info(f"   Intervalle     : {POST_INTERVAL}s ({POST_INTERVAL//3600}h)")
    log.info(f"   Annonces IA    : {NB_ANNONCES} (Gemini → Groq → fallback)")
    log.info("=" * 50)

    bot = Bot(token=BOT_TOKEN)
    annonces = load_annonces()
    annonce_index = 0

    while True:
        now = datetime.now()

        # Publier immédiatement au démarrage
        annonce_index = await publish_annonces(bot, annonces, annonce_index)

        # Attendre jusqu'à la prochaine heure pile (ou intervalle configuré)
        if POST_INTERVAL == 3600:
            next_run = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        else:
            next_run = now + timedelta(seconds=POST_INTERVAL)

        wait_seconds = max(0, (next_run - datetime.now()).total_seconds())
        log.info(f"😴 Prochaine publication à {next_run.strftime('%H:%M:%S')} (attente: {int(wait_seconds)}s)")
        await asyncio.sleep(wait_seconds)

async def main():
    while True:
        try:
            await main_loop()
        except Exception as e:
            log.error(f"💥 Erreur fatale : {e} — redémarrage dans 10s...")
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Bot arrêté.")
