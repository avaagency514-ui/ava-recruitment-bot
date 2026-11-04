"""
ava-recruitment-bot
Bot Telegram de publication d'annonces de recrutement via Telethon (API_ID / API_HASH / User Account).
- Utilise Telethon pour poster en tant que compte utilisateur dans les groupes publics
- Génère 3-5 annonces variées au démarrage via Gemini API (fallback: Groq / templates officiels)
- Les publie en rotation dans les groupes Telegram configurés (@ofmva_fr, @jobonlinevas...)
- Publication sécurisée avec délai aléatoire anti-flood
- Reconnexion automatique infinie (Railway 24/7)
"""

import os
import sys
import json
import asyncio
import logging
import random
import time
from datetime import datetime, timedelta

import requests
from telethon import TelegramClient
from telethon.sessions import StringSession

# ─── Logging vers stdout (Railway) ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("RecruiterTelethon")

# ─── Configuration depuis variables d'environnement ───────────────────────────
API_ID         = int(os.environ.get("TELEGRAM_API_ID", "36121361"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "29263ae8f125a5dfb91491b63264d0e2").strip()
STRING_SESSION = os.environ.get("TELEGRAM_STRING_SESSION", "").strip()
SESSION_FILE   = os.environ.get("TELEGRAM_SESSION_FILE", "recruiter")

DEFAULT_GROUPS = "@ofmva_fr, @jobonlinevas, @ofmanagementgroupe"
TARGET_GROUPS  = [g.strip() for g in os.environ.get("TARGET_GROUPS", DEFAULT_GROUPS).split(",") if g.strip()]

POST_INTERVAL  = int(os.environ.get("POST_INTERVAL", "3600"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
NB_ANNONCES    = int(os.environ.get("NB_ANNONCES", "5"))

# ─── EXEMPLES DE POSTS RÉFÉRENCE (style exact de l'agence) ───────────────────
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

ANNONCES_FALLBACK = EXEMPLES_REFERENCE.copy()

# ─── Génération IA via Gemini ─────────────────────────────────────────────────
def generate_via_gemini(prompt: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
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

# ─── Génération IA via Groq (fallback) ───────────────────────────────────────
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

Voici un exemple de post de recrutement officiel que nous utilisons :
---
{exemple}
---

Génère un NOUVEAU post de recrutement percutant pour le poste : **{poste}**
Style attendu : {style}

Contraintes STRICTES :
- Garde le format structuré (émojis, sections, contact à la fin)
- Se termine obligatoirement par "Envoie-nous un message privé directement pour passer ton premier entretien @rcruting_bot" (ou présenter ton parcours)
- Français impeccable, captivant et professionnel
- Maximum 25 lignes
- Renvoie UNIQUEMENT le texte du post, sans texte introductif."""

def generate_annonce(index: int) -> str:
    prompt = build_prompt(index)
    text = generate_via_gemini(prompt) or generate_via_groq(prompt)
    if text:
        return text
    log.warning(f"⚠️ IA indisponible pour annonce {index+1} — utilisation du modèle de base")
    return ANNONCES_FALLBACK[index % len(ANNONCES_FALLBACK)]

def load_annonces() -> list[str]:
    log.info(f"🤖 Génération de {NB_ANNONCES} annonces via IA (Gemini → Groq → fallback)...")
    annonces = []
    for i in range(NB_ANNONCES):
        log.info(f"  → Génération annonce {i+1}/{NB_ANNONCES} ({TYPES_POSTES[i % len(TYPES_POSTES)][0]})...")
        annonces.append(generate_annonce(i))
        time.sleep(1.5)
    log.info(f"✅ {len(annonces)} annonces prêtes pour la rotation.")
    return annonces

# ─── Client Telethon ─────────────────────────────────────────────────────────
def init_telethon_client() -> TelegramClient:
    if STRING_SESSION:
        log.info("🔑 Utilisation de StringSession depuis variable d'environnement")
        return TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

    # Chemin du fichier .session
    base_dir = os.path.dirname(os.path.abspath(__file__))
    session_path = os.path.join(base_dir, SESSION_FILE)
    log.info(f"📁 Utilisation du fichier session : {session_path}.session")
    return TelegramClient(session_path, API_ID, API_HASH)

# ─── Envoi d'une tournée dans les groupes ────────────────────────────────────
async def publish_round(client: TelegramClient, annonces: list[str], annonce_index: int) -> int:
    if not annonces:
        log.warning("⚠️ Aucune annonce disponible.")
        return annonce_index

    idx = annonce_index % len(annonces)
    annonce = annonces[idx]
    poste_name = TYPES_POSTES[idx % len(TYPES_POSTES)][0]

    log.info(f"📢 Tournée de publication [{poste_name}] ({idx+1}/{len(annonces)}) dans {len(TARGET_GROUPS)} groupe(s)...")

    for groupe in TARGET_GROUPS:
        try:
            await client.send_message(groupe, annonce)
            log.info(f"  ✅ Posté avec succès dans {groupe}")
            # Pause aléatoire anti-flood (6 à 12 secondes)
            sleep_time = random.randint(6, 12)
            await asyncio.sleep(sleep_time)
        except Exception as e:
            log.error(f"  ⚠️ Erreur envoi dans {groupe}: {e}")

    return annonce_index + 1

# ─── Boucle principale ────────────────────────────────────────────────────────
async def main_loop():
    log.info("=" * 60)
    log.info("🚀 AVA Agency — Bot Recrutement Telethon (API_ID & API_HASH)")
    log.info(f"   API_ID         : {API_ID}")
    log.info(f"   Groupes cibles : {', '.join(TARGET_GROUPS)}")
    log.info(f"   Intervalle     : {POST_INTERVAL}s ({POST_INTERVAL // 3600}h)")
    log.info(f"   Gemini API     : {'✅ Activé' if GEMINI_API_KEY else '❌ Non configuré'}")
    log.info(f"   Groq API       : {'✅ Activé' if GROQ_API_KEY else '❌ Non configuré'}")
    log.info("=" * 60)

    client = init_telethon_client()
    await client.connect()

    if not await client.is_user_authorized():
        log.critical("❌ Le compte Telegram n'est PAS autorisé ou la session est expirée !")
        log.critical("Vérifiez le fichier recruiter.session ou la variable TELEGRAM_STRING_SESSION.")
        return

    me = await client.get_me()
    log.info(f"✅ Connecté à Telegram en tant que : {me.first_name} (@{me.username or 'sans_username'}, Tel: +{me.phone})")

    annonces = load_annonces()
    annonce_index = 0

    while True:
        now = datetime.now()

        # Envoi de la tournée
        annonce_index = await publish_round(client, annonces, annonce_index)

        # Pause jusqu'au prochain intervalle
        if POST_INTERVAL == 3600:
            next_run = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        else:
            next_run = now + timedelta(seconds=POST_INTERVAL)

        wait_seconds = max(10, (next_run - datetime.now()).total_seconds())
        log.info(f"😴 Prochaine tournée à {next_run.strftime('%H:%M:%S')} (attente: {int(wait_seconds)}s)")
        await asyncio.sleep(wait_seconds)

async def main():
    while True:
        try:
            await main_loop()
        except Exception as e:
            log.error(f"💥 Erreur dans main_loop: {e} — redémarrage dans 15s...")
            await asyncio.sleep(15)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Arrêté.")
