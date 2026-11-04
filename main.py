"""
ava-recruitment-bot
Bot Telegram de publication d'annonces de recrutement via Telethon (API_ID / API_HASH / User Account).
- Compte Telegram : +261381789477 (API_ID: 36121361, API_HASH: 29263ae8f125a5dfb91491b63264d0e2)
- Fichier session : recruiter.session (pré-authentifié)
- Charge automatiquement les 137 groupes de recrutement depuis groupes_scanned.json
- Exclut automatiquement tous les groupes internes privés de l'agence AVA
- Génère 5 annonces variées via FreeLLM / Gemini API (fallback: modèles officiels)
- Intervalle fixe : 20 minutes entre chaque tournée de publication
- Délais aléatoires anti-flood (7 à 12s) entre chaque groupe
- Support des Topics / Forums Telegram
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
from telethon.tl.functions.messages import GetForumTopicsRequest

# ─── Logging vers stdout (Railway) ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("RecruiterTelethon")

# ─── Configuration ────────────────────────────────────────────────────────────
API_ID         = int(os.environ.get("TELEGRAM_API_ID", "36121361"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "29263ae8f125a5dfb91491b63264d0e2").strip()
PHONE_NUMBER   = os.environ.get("TELEGRAM_PHONE", "+261381789477").strip()
STRING_SESSION = os.environ.get("TELEGRAM_STRING_SESSION", "").strip()
SESSION_FILE   = os.environ.get("TELEGRAM_SESSION_FILE", "recruiter")

# ⏱️ 20 minutes fixes entre chaque tournée (1200 secondes)
POST_INTERVAL  = int(os.environ.get("POST_INTERVAL", "1200"))

# Clés IA (Gemini ou FreeLLM) configurées dans les variables d'environnement
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "").strip()
FREELLM_API_KEY = os.environ.get("FREELLM_API_KEY", "").strip()
FREELLM_API_URL = os.environ.get("FREELLM_API_URL", "https://api.freellm.io/v1").rstrip("/")
NB_ANNONCES     = int(os.environ.get("NB_ANNONCES", "5"))

# Mots-clés pour exclure absolument les salons privés de l'agence AVA
INTERNAL_EXCLUDED = [
    "ava agency", "ava ", "kim", "isabella", "isabele", "nailys",
    "jenny", "johanna", "johannah", "marvin", "carla", "julie", "diablo",
    "hervé", "antiland", "modèle gasy", "ldplayer", "camille lin", "threads kim",
    "faïz", "ricardo", "chez jarb"
]

# ─── Chargement des groupes cibles ───────────────────────────────────────────
def load_target_groups():
    env_groups = os.environ.get("TARGET_GROUPS", "").strip()
    if env_groups:
        groups = [g.strip() for g in env_groups.split(",") if g.strip()]
        log.info(f"🎯 {len(groups)} groupes configurés via variable TARGET_GROUPS.")
        return groups

    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "groupes_scanned.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_groups = data.get(PHONE_NUMBER, {}).get("groups", [])
            if not raw_groups:
                for key in data.keys():
                    if key.replace("+", "").replace(" ", "") in PHONE_NUMBER.replace("+", "").replace(" ", ""):
                        raw_groups = data[key].get("groups", [])
                        break

            filtered = []
            for g in raw_groups:
                title = g.get("title", "").lower()
                entry = g.get("entry", "").strip()
                if not entry:
                    continue
                if any(bad in title for bad in INTERNAL_EXCLUDED):
                    continue
                filtered.append(entry)

            if filtered:
                log.info(f"📂 {len(filtered)} groupes de recrutement publics chargés depuis groupes_scanned.json (salons internes exclus).")
                return filtered
        except Exception as e:
            log.warning(f"⚠️ Erreur lecture groupes_scanned.json : {e}")

    fallback = ["@ofmva_fr", "@jobonlinevas", "@ofmanagementgroupe"]
    log.info(f"ℹ️ Utilisation des groupes par défaut : {fallback}")
    return fallback

# ─── EXEMPLES DE POSTS RÉFÉRENCE ─────────────────────────────────────────────
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

# ─── Génération IA via FreeLLM ────────────────────────────────────────────────
def generate_via_freellm(prompt: str) -> str | None:
    if not FREELLM_API_KEY:
        return None
    models = ["gemini-3.8-flash", "gemini-3.5-flash", "llama-3.3-70b-fp8-fast", "mistral-small-3.1-24b"]
    for model_name in models:
        try:
            url = f"{FREELLM_API_URL}/chat/completions"
            headers = {"Authorization": f"Bearer {FREELLM_API_KEY}", "Content-Type": "application/json"}
            body = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.95
            }
            res = requests.post(url, headers=headers, json=body, timeout=20)
            if res.status_code == 200:
                data = res.json()
                text = data["choices"][0]["message"]["content"].strip()
                log.info(f"✅ Annonce générée via FreeLLM ({model_name})")
                return text
        except Exception:
            continue
    return None

# ─── Génération IA via Gemini Direct ──────────────────────────────────────────
def generate_via_gemini(prompt: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.95, "maxOutputTokens": 700}
        }
        res = requests.post(url, json=body, timeout=20)
        if res.status_code == 200:
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            log.info("✅ Annonce générée via Gemini direct")
            return text
    except Exception:
        pass
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
    text = generate_via_freellm(prompt) or generate_via_gemini(prompt)
    if text:
        return text
    log.warning(f"⚠️ IA indisponible pour annonce {index+1} — utilisation du modèle officiel")
    return ANNONCES_FALLBACK[index % len(ANNONCES_FALLBACK)]

def load_annonces() -> list[str]:
    log.info(f"🤖 Génération de {NB_ANNONCES} annonces via IA (FreeLLM / Gemini)...")
    annonces = []
    for i in range(NB_ANNONCES):
        log.info(f"  → Génération annonce {i+1}/{NB_ANNONCES} ({TYPES_POSTES[i % len(TYPES_POSTES)][0]})...")
        annonces.append(generate_annonce(i))
        time.sleep(1)
    log.info(f"✅ {len(annonces)} annonces prêtes pour la rotation.")
    return annonces

# ─── Client Telethon ─────────────────────────────────────────────────────────
def init_telethon_client() -> TelegramClient:
    if STRING_SESSION:
        log.info("🔑 Utilisation de StringSession depuis variable d'environnement")
        return TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    session_path = os.path.join(base_dir, SESSION_FILE)
    log.info(f"📁 Utilisation du fichier session : {session_path}.session")
    return TelegramClient(session_path, API_ID, API_HASH)

# ─── Envoi d'un message avec gestion Forum / Topic ───────────────────────────
async def send_to_target(client: TelegramClient, entry: str, msg: str):
    group_name = entry
    topic_id = None

    if entry.startswith("https://t.me/"):
        parts = entry.replace("https://t.me/", "").split("/")
        group_name = "@" + parts[0]
        if len(parts) >= 2 and parts[1].isdigit():
            topic_id = int(parts[1])
    elif ":" in entry and not entry.startswith("http"):
        g, t = entry.rsplit(":", 1)
        group_name = g.strip()
        topic_id = int(t.strip()) if t.strip().isdigit() else None

    if topic_id:
        target = int(group_name) if str(group_name).lstrip('-').isdigit() else group_name
        await client.send_message(target, msg, reply_to=topic_id)
        return

    target = int(group_name) if str(group_name).lstrip('-').isdigit() else group_name
    entity = await client.get_entity(target)

    if getattr(entity, 'forum', False):
        reply_to_msg_id = 1
        try:
            topics_req = await client(GetForumTopicsRequest(
                channel=entity, offset_date=0, offset_id=0, offset_topic=0, limit=5, q=''
            ))
            for t in getattr(topics_req, 'topics', []):
                if getattr(t, 'id', None) and not getattr(t, 'closed', False):
                    reply_to_msg_id = t.id
                    break
        except Exception:
            pass
        await client.send_message(entity, msg, reply_to=reply_to_msg_id)
    else:
        await client.send_message(entity, msg)

# ─── Tournée de publication dans les groupes ─────────────────────────────────
async def publish_round(client: TelegramClient, annonces: list[str], annonce_index: int, target_groups: list[str]) -> int:
    if not annonces or not target_groups:
        log.warning("⚠️ Aucune annonce ou aucun groupe disponible.")
        return annonce_index

    idx = annonce_index % len(annonces)
    annonce = annonces[idx]
    poste_name = TYPES_POSTES[idx % len(TYPES_POSTES)][0]

    log.info(f"📢 Début tournée [{poste_name}] ({idx+1}/{len(annonces)}) vers {len(target_groups)} groupe(s)...")

    succes = 0
    erreurs = 0

    for entry in target_groups:
        try:
            await send_to_target(client, entry, annonce)
            succes += 1
            log.info(f"  ✅ Posté dans {entry} ({succes}/{len(target_groups)})")
            await asyncio.sleep(random.randint(7, 12))
        except Exception as e:
            erreurs += 1
            log.warning(f"  ⚠️ Erreur envoi {entry} : {str(e)[:100]}")
            await asyncio.sleep(3)

    log.info(f"🏁 Tournée terminée : {succes} envoyés, {erreurs} erreurs.")
    return annonce_index + 1

# ─── Boucle principale (20 minutes fixes) ────────────────────────────────────
async def main_loop():
    target_groups = load_target_groups()

    log.info("=" * 65)
    log.info("🚀 AVA Agency — Bot Recrutement Telethon (20 min fixes)")
    log.info(f"   Compte         : {PHONE_NUMBER}")
    log.info(f"   Groupes cibles : {len(target_groups)} groupes chargés")
    log.info(f"   Intervalle     : {POST_INTERVAL}s (20 minutes fixes)")
    log.info(f"   Moteur IA      : FreeLLM & Gemini API intégrés")
    log.info("=" * 65)

    client = init_telethon_client()
    await client.connect()

    if not await client.is_user_authorized():
        log.critical("❌ Le compte Telegram n'est PAS autorisé ou la session est expirée !")
        return

    me = await client.get_me()
    log.info(f"✅ Connecté en tant que : {me.first_name} (@{me.username or 'sans_username'}, Tel: +{me.phone})")

    annonces = load_annonces()
    annonce_index = 0

    while True:
        now = datetime.now()

        # Envoi de la tournée
        annonce_index = await publish_round(client, annonces, annonce_index, target_groups)

        # ⏱️ Pause de 20 minutes fixes (1200 secondes)
        next_run = now + timedelta(seconds=POST_INTERVAL)
        wait_seconds = max(10, (next_run - datetime.now()).total_seconds())
        log.info(f"😴 Prochaine tournée dans 20 minutes (à {next_run.strftime('%H:%M:%S')})")
        await asyncio.sleep(wait_seconds)

async def main():
    while True:
        try:
            await main_loop()
        except Exception as e:
            log.error(f"💥 Erreur main_loop: {e} — reprise dans 15s...")
            await asyncio.sleep(15)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Arrêté.")
