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
import time
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
POST_INTERVAL  = int(os.environ.get("POST_INTERVAL", "3600"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
NB_ANNONCES    = int(os.environ.get("NB_ANNONCES", "5"))

# ─── EXEMPLES DE POSTS RÉFÉRENCE (style exact voulu par l'agence) ─────────────
EXEMPLES_REFERENCE = [
    """🚀 RECRUTEMENT : REJOINS NOTRE ÉQUIPE D'ASSISTANTS VIRTUELS (VA)

Notre agence s'agrandit et nous recherchons des VAs motivés et rigoureux pour gérer et développer nos canaux de trafic.

💼 Ce que nous t'offrons :

🎓 Formation complète offerte : Pas besoin d'expérience préalable, nous te formons à nos méthodes.

💵 Rémunération claire & transparente : Système de paie bimensuel avec conservation de tes points et primes de performance.

🏠 100 % à distance : Travaille depuis chez toi, avec ton ordinateur/smartphone et une bonne connexion.

📈 Perspectives d'évolution : Possibilité de passer Manager selon tes résultats.

📋 Profil recherché :

Rigoureux(se), autonome et à l'écoute des consignes.
À l'aise avec les réseaux sociaux et la messagerie Telegram.
Disponible quotidiennement.

📩 Comment postuler ?
Envoie-nous un message privé directement pour passer ton premier entretien @rcruting_bot""",

    """🔥 RECRUTEMENT CHATTER EXPÉRIMENTÉ(E) — REJOINS NOTRE AGENCE !

Tu maîtrises l'art de la discussion, de l'engagement et de la conversion sur les réseaux sociaux ? Notre agence cherche des chatters motivés et talentueux pour dynamiser ses comptes.

💰 Une rémunération sur-mesure :

Pourcentage selon ton expérience : Ici, tes compétences sont valorisées à leur juste valeur. Plus tu as d'expérience et de résultats, plus ton pourcentage de commission est élevé !

Paiements réguliers, sécurisés et transparents.

💼 Profil recherché :

Expérience préalable exigée en tant que chatter (gestion de communautés ou de profils).
Excellente aisance relationnelle et rédactionnelle.
Sérieux, rigoureux et disponible.
Bonne connexion internet et équipement adapté (PC/téléphone).

📩 Comment postuler ?
Envoie-nous un message privé directement pour nous présenter ton parcours ! @rcruting_bot"""
]

# ─── Annonces statiques de secours (si toutes les IA échouent) ───────────────
ANNONCES_FALLBACK = EXEMPLES_REFERENCE.copy()

# ─── Génération via Gemini API ────────────────────────────────────────────────
def generate_via_gemini(prompt: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.95, "maxOutputTokens": 700}
        }
        res = requests.post(url, json=body, timeout=25)
        if res.status_code == 200:
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            log.info("✅ Annonce générée via Gemini")
            return text
        log.warning(f"⚠️ Gemini HTTP {res.status_code}: {res.text[:120]}")
    except Exception as e:
        log.warning(f"⚠️ Erreur Gemini : {e}")
    return None

# ─── Génération via Groq (fallback) ──────────────────────────────────────────
def generate_via_groq(prompt: str) -> str | None:
    if not GROQ_API_KEY:
        return None
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.95,
                "max_tokens": 700
            },
            timeout=25
        )
        if res.status_code == 200:
            text = res.json()["choices"][0]["message"]["content"].strip()
            log.info("✅ Annonce générée via Groq (fallback)")
            return text
        log.warning(f"⚠️ Groq HTTP {res.status_code}: {res.text[:120]}")
    except Exception as e:
        log.warning(f"⚠️ Erreur Groq : {e}")
    return None

# ─── Prompt de génération basé sur les exemples de l'agence ──────────────────
TYPES_POSTES = [
    ("Assistant Virtuel (VA) débutant", "motivant, accessible, met en avant la formation offerte"),
    ("Chatter expérimenté", "professionnel, valorise l'expérience et la commission élevée"),
    ("VA Instagram mobile (iPhone)", "dynamique, met en avant la flexibilité et le paiement crypto"),
    ("VA Instagram sur PC", "technique, met en avant la puissance du PC et les gains"),
    ("Manager en devenir", "ambitieux, met en avant l'évolution de carrière possible"),
]

def build_prompt(index: int) -> str:
    poste, style = TYPES_POSTES[index % len(TYPES_POSTES)]
    exemple = EXEMPLES_REFERENCE[index % len(EXEMPLES_REFERENCE)]

    return f"""Tu es le responsable recrutement d'AVA Agency, une agence digitale française.

Voici un exemple de post de recrutement que nous utilisons :
---
{exemple}
---

Maintenant, génère un NOUVEAU post de recrutement pour le poste suivant : **{poste}**
Style attendu : {style}

Contraintes OBLIGATOIRES :
- Garde exactement le même format et la même structure que l'exemple (émojis, sections, @rcruting_bot à la fin)
- Le post doit se terminer par "Envoie-nous un message privé directement à @rcruting_bot"
- Varie le titre, les formulations et les arguments par rapport à l'exemple
- Reste professionnel, motivant et en français
- Maximum 25 lignes
- Écris UNIQUEMENT le post, sans introduction ni commentaire."""

# ─── Génération d'une annonce : Gemini → Groq → fallback ─────────────────────
def generate_annonce(index: int) -> str:
    prompt = build_prompt(index)

    text = generate_via_gemini(prompt)
    if text:
        return text

    text = generate_via_groq(prompt)
    if text:
        return text

    log.warning(f"⚠️ IA indisponible pour annonce {index+1} — utilisation du post de référence")
    return ANNONCES_FALLBACK[index % len(ANNONCES_FALLBACK)]

# ─── Chargement des annonces au démarrage ────────────────────────────────────
def load_annonces() -> list[str]:
    log.info(f"🤖 Génération de {NB_ANNONCES} annonces via IA (Gemini → Groq → fallback)...")
    annonces = []
    for i in range(NB_ANNONCES):
        log.info(f"  → Génération annonce {i+1}/{NB_ANNONCES} (poste: {TYPES_POSTES[i % len(TYPES_POSTES)][0]})...")
        annonce = generate_annonce(i)
        annonces.append(annonce)
        time.sleep(1.5)  # Anti-rate-limit
    log.info(f"✅ {len(annonces)} annonces prêtes pour la rotation.")
    return annonces

# ─── Publication dans les groupes Telegram ───────────────────────────────────
async def publish_round(bot: Bot, annonces: list[str], annonce_index: int) -> int:
    if not annonces:
        log.warning("⚠️ Aucune annonce disponible.")
        return annonce_index

    idx = annonce_index % len(annonces)
    annonce = annonces[idx]
    horodatage = datetime.now().strftime("%d/%m/%Y %H:%M")
    ref = f"REF-{datetime.now().strftime('%Y%m%d%H%M')}"

    # Pas de footer visible pour garder le post naturel
    full_message = annonce

    poste_name = TYPES_POSTES[idx % len(TYPES_POSTES)][0]
    log.info(f"📢 Publication [{poste_name}] dans {len(TARGET_GROUPS)} groupe(s)...")

    for groupe in TARGET_GROUPS:
        try:
            await bot.send_message(
                chat_id=groupe,
                text=full_message,
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

    log.info("=" * 55)
    log.info("🚀 AVA Agency — Bot Recrutement IA (Railway 24/7)")
    log.info(f"   Groupes cibles   : {len(TARGET_GROUPS)}")
    log.info(f"   Intervalle       : {POST_INTERVAL}s ({POST_INTERVAL // 3600}h)")
    log.info(f"   Annonces IA      : {NB_ANNONCES} (Gemini → Groq → fallback)")
    log.info(f"   Gemini API       : {'✅ Configurée' if GEMINI_API_KEY else '❌ Non configurée'}")
    log.info(f"   Groq API         : {'✅ Configurée' if GROQ_API_KEY else '❌ Non configurée'}")
    log.info("=" * 55)

    bot = Bot(token=BOT_TOKEN)
    annonces = load_annonces()
    annonce_index = 0

    while True:
        now = datetime.now()

        # Publication immédiate
        annonce_index = await publish_round(bot, annonces, annonce_index)

        # Attente jusqu'à l'heure pile suivante (ou intervalle configuré)
        if POST_INTERVAL == 3600:
            next_run = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        else:
            next_run = now + timedelta(seconds=POST_INTERVAL)

        wait_seconds = max(10, (next_run - datetime.now()).total_seconds())
        log.info(f"😴 Prochaine publication à {next_run.strftime('%H:%M:%S')} (attente: {int(wait_seconds)}s)")
        await asyncio.sleep(wait_seconds)

# ─── Entry point avec redémarrage automatique ────────────────────────────────
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
