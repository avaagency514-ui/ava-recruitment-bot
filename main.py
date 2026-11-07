"""
ava-recruitment-bot
Bot Telegram de publication d'annonces de recrutement via Telethon (API_ID / API_HASH / User Account).
- Compte Telegram : +261381789477 (API_ID: 36121361, API_HASH: 29263ae8f125a5dfb91491b63264d0e2)
- Fichier session : recruiter.session (pré-authentifié)
- Charge automatiquement les 137 groupes de recrutement depuis groupes_scanned.json
- Exclut automatiquement tous les groupes internes privés de l'agence AVA
- 5 modèles officiels de recrutement 100% VA (Instagram, Facebook, Jailbreak, Twitter, Twitter & Threads)
- Rémunération au sub, paiement toutes les 2 semaines en Crypto USDT, contact @rcruting_bot
- Diffusion aléatoire à chaque tournée
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
import base64
from datetime import datetime, timedelta, timezone

import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

# ─── Configuration encodage UTF-8 ────────────────────────────────────────────
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

# Notifications Discord dans #log-rcrutement
_DEF_DS = base64.b64decode("TVRVek16QTVNVGsyTXpBeU16RXpNRFkyTkEuR0JUOGRPLkdZd0lMMUw0UHpVeGR5S25fUElyU1RkMzZQdGdmMHZaTVEwVjQ4").decode()
DISCORD_BOT_TOKEN   = (os.environ.get("DISCORD_BOT_TOKEN") or _DEF_DS).strip()
DISCORD_LOG_CHANNEL = (os.environ.get("DISCORD_LOG_CHANNEL_ID") or "1564832120067596318").strip()

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

# ─── LES 5 ANNONCES OFFICIELLES 100% VA ───────────────────────────────────────
VA_OFFICIAL_TEMPLATES = [
    {
        "id": "insta",
        "poste": "VA Instagram",
        "texte": """📢 RECRUTEMENT – INSTAGRAM (MARCHÉ FR 🇫🇷) !

Tu souhaites travailler à distance directement depuis ton smartphone ? Nous recherchons de nouveaux profils pour développer notre équipe spécialisée dans la gestion et le développement de comptes Instagram !

🎯 TRAFIC STRICTEMENT FRANÇAIS (FR 🇫🇷) :
Marché 100% France uniquement.

📩 Contact : @rcruting_bot 📩 

💰 RÉMUNÉRATION & MODALITÉS :
- Rémunération au sub (au nombre d'abonnés français qualifiés générés) 🎯
- Jusqu'à 350 USDT selon tes performances
- Paiement toutes les 2 semaines 📆
- Règlement sécurisé en Crypto USDT 💵
- Bonus et primes de résultats 🤑
- Possibilités d'évolution rapide

📱 MATÉRIEL :
- iPhone et Android acceptés
- Jailbreak = un plus, mais pas obligatoire
- Connexion Internet stable

🔥 PROFIL RECHERCHÉ :
- Débutants acceptés
- Bonne disponibilité
- Sérieux et régularité
- Envie d'apprendre et de progresser

🎓 ACCOMPAGNEMENT :
- Formation complète
- Stratégies Instagram performantes 📈
- Suivi personnalisé par des Managers
- Calls et accompagnement régulier

Nous recherchons des personnes motivées, prêtes à s'investir et à évoluer avec nous sur le long terme.

📩 Intéressé(e) ? Envoie un DM à @rcruting_bot avec une petite présentation de toi ! 📩"""
    },
    {
        "id": "facebook",
        "poste": "VA Facebook / Réseaux Sociaux",
        "texte": """📢 RECRUTEMENT — VA FACEBOOK / RÉSEAUX SOCIAUX

Tu publies nos vidéos sur une page créée avec ton propre compte. Aucune expérience requise : formation complète assurée sur Discord.

💰 RÉMUNÉRATION AU SUB :
Plus tu génères de subs (abonnés qualifiés), plus tu gagnes. Possibilité de dépasser 500 USDT par session de 2 semaines, sans aucun plafond.

📆 PAIEMENT & MODALITÉS :
- Paiement garanti toutes les 2 semaines (tous les 14 jours).
- Paiement par Crypto USDT (TRC-20 / Solana).
- Rémunération 100% basée sur les subs générés.

⚠️ CRITÈRES DE QUALITÉ & TRAFIC :
Trafic STRICTEMENT FRANCE 🇫🇷 : seuls les abonnés français comptent. Tracking transparent et vérifiable en direct.

📱 MATÉRIEL :
Smartphone + 4G/5G suffisent. Vidéos, formation et lien personnel fournis par l'agence.

✅ Recherche de profils sérieux, motivés et réguliers.

✉️ Contacte @rcruting_bot en message privé pour postuler !"""
    },
    {
        "id": "jailbreak",
        "poste": "VA Instagram Jailbreak",
        "texte": """🔓 RECRUTEMENT VA — IPHONE JAILBREAKÉ 🔓

💸 JUSQU'À 300 USDT / SESSION DE 2 SEMAINES

💰 Rémunération au sub (nombre d'abonnements qualifiés)
💵 Payé toutes les 2 semaines en Crypto USDT
✅ iPhone jailbreaké obligatoire
🇫🇷 Trafic STRICTEMENT FRANCE 🇫🇷 (Marché français uniquement)
⏰ 1 à 2h par jour seulement
📈 Outils automatisés et accompagnement fournis

🔥 Les places partent très vite ! Contacte @rcruting_bot en DM pour rejoindre l'équipe."""
    },
    {
        "id": "twitter",
        "poste": "VA Twitter / X (Marché FR 🇫🇷)",
        "texte": """📍 RECRUTEMENT VA TWITTER / X (UNIQUEMENT 🇲🇬 🇧🇯 🇨🇲)

Nous recrutons des personnes motivées pour gérer des comptes Twitter / X : création de comptes, publication de contenu, interactions et chatting.

🎯 Cible : Trafic STRICTEMENT FRANCE 🇫🇷

💰 RÉMUNÉRATION AU NOMBRE D'ABONNEMENTS (SUBS) :
• Rémunération basée sur le nombre de subs français générés
• Paiement toutes les 2 semaines
• Règlement en Crypto USDT
• Tracking clair, fiable et transparent
• Très bonne rémunération pour les profils performants

📈 OPPORTUNITÉS D’ÉVOLUTION :
• Plus de responsabilités et primes d'excellence
• Meilleures conditions de rémunération au mérite
• Possibilité d’évoluer au sein de l'agence

🎯 PROFIL RECHERCHÉ :
• Ouvert à tous (débutants motivés acceptés)
• À l’aise avec Twitter / X et la communication écrite en français
• Sérieux, motivé et régulier
• Formation complète fournie

📩 Intéressé(e) ? Envoie un DM à @rcruting_bot avec ta présentation ! (Marché FR 🇫🇷)"""
    },
    {
        "id": "xthreads",
        "poste": "VA Twitter & Threads",
        "texte": """🚀 RECRUTEMENT — VA X (TWITTER) & THREADS 🚀

Je cherche des profils expérimentés pour gérer et scaler du trafic via X (Twitter) + Threads. 📱&📱

🎯 Trafic STRICTEMENT FRANCE 🇫🇷 (audience 100% française).

⚡️ Pourquoi nous rejoindre :
– Stratégie déjà prête + process clair et rodé
– Contenu + angles optimisés fournis
– Environnement orienté performance (on scale ce qui marche)
– Possibilité d’évolution + missions supplémentaires

---
💼 Mission :
– Analyser les meilleurs posts (X + Threads)
– Programmer les contenus sur 7 jours
– Optimiser le reach & l’engagement
– Analyser les résultats + reporting

⌛️ Temps de travail :
– ~4h30 / semaine
– 1 jour fixe / semaine (tu choisis ton créneau)

---
💵 Rémunération & Paiement :
– Rémunération au sub (selon le volume d'abonnés français convertis)
– Paiement garanti toutes les 2 semaines
– Règlement en Crypto USDT
– Évolution possible + cumul avec d’autres missions au sein de l'agence

---
⚠️ Profil recherché :
– Expérience réelle sur les réseaux sociaux 
– À l’aise avec X / Threads (growth, contenu, hooks)
– Autonome, rapide, orienté résultats
– Ordinateur obligatoire 💻

⭐ On cherche des profils solides qui veulent performer et évoluer. Pas de débutants.

---
📩 Pour postuler :

DM @rcruting_bot pour postuler ! 📈"""
    },
    {
        "id": "chatter",
        "poste": "Chatter Expérimenté(e)",
        "texte": """🔥 RECRUTEMENT CHATTER EXPÉRIMENTÉ(E) — REJOINS NOTRE AGENCE !

Tu maîtrises l'art de la discussion, de l'engagement et de la conversion ? Notre agence recrute des chatters motivés et talentueux pour dynamiser ses comptes.

🎯 Cible : Trafic STRICTEMENT FRANCE 🇫🇷 (conversations en français).

💰 RÉMUNÉRATION & AVANTAGES :
• Rémunération au pourcentage selon tes performances
• Jusqu'à 15% de commission + primes de résultats 🤑
• Paiement toutes les 2 semaines (tous les 14 jours) 📆
• Règlement sécurisé en Crypto USDT 💵
• Possibilités d'évolution rapide au sein de l'agence

💼 PROFIL RECHERCHÉ :
• Expérience requise en tant que chatter (OFM / réseaux sociaux)
• Excellente aisance relationnelle et orthographe française irréprochable
• Sérieux, autonome, rigoureux et disponible
• Ordinateur et/ou smartphone avec connexion stable

🎓 ACCOMPAGNEMENT :
• Process rodés et organisation d'équipe claire
• Suivi personnalisé par les Managers

📩 Pour postuler :
DM @rcruting_bot avec une courte présentation de ton parcours ! 📈"""
    }
]

# Tirage aléatoire sans répétition immédiate (deck mélangé de 6 postes)
current_deck = []

def get_next_random_template():
    global current_deck
    if not current_deck:
        current_deck = VA_OFFICIAL_TEMPLATES.copy()
        random.shuffle(current_deck)
        log.info("🎲 Nouveau deck de 6 annonces de recrutement mélangé pour la diffusion aléatoire.")
    return current_deck.pop()

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

# ─── Notifications Discord dans #log-rcrutement ──────────────────────────────
def notify_discord_startup(phone: str, me_name: str, total_groups: int):
    if not DISCORD_BOT_TOKEN or not DISCORD_LOG_CHANNEL:
        return
    embed = {
        "title": "🚀 Bot Recrutement Connecté & Actif",
        "description": f"Le compte Telegram **{me_name}** (`{phone}`) est connecté et prêt à publier.",
        "color": 0x2ECC71,  # Vert
        "fields": [
            {"name": "👥 Groupes cibles", "value": f"**{total_groups}** groupes chargés", "inline": True},
            {"name": "⏱️ Cadence", "value": "Toutes les **20 minutes fixes**", "inline": True},
            {"name": "🎲 Rotation", "value": "6 modèles officiels (5 VA + 1 Chatter en aléatoire)", "inline": True}
        ],
        "footer": {"text": "AVA Agency — Bot Recrutement Telethon • Salon #log-rcrutement"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{DISCORD_LOG_CHANNEL}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"},
            json={"embeds": [embed]},
            timeout=10
        )
    except Exception as e:
        log.warning(f"Erreur notification startup Discord : {e}")

def notify_discord_round_start(poste_name: str, total_targets: int, annonce_text: str):
    if not DISCORD_BOT_TOKEN or not DISCORD_LOG_CHANNEL:
        return
    embed = {
        "title": "🚀 Nouvelle Tournée en cours d'envoi...",
        "description": f"Le bot commence à publier dans les **{total_targets} groupes Telegram**.",
        "color": 0xF39C12,  # Orange
        "fields": [
            {"name": "🎯 Poste ciblé", "value": f"**{poste_name}**", "inline": True},
            {"name": "👥 Cibles", "value": f"**{total_targets}** groupes de recrutement", "inline": True},
            {"name": "📝 Annonce officielle", "value": f"```{annonce_text[:850]}```", "inline": False}
        ],
        "footer": {"text": "AVA Agency — Bot Recrutement Telethon • Salon #log-rcrutement"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{DISCORD_LOG_CHANNEL}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"},
            json={"embeds": [embed]},
            timeout=10
        )
    except Exception:
        pass

def notify_discord_error(msg: str):
    if not DISCORD_BOT_TOKEN or not DISCORD_LOG_CHANNEL:
        return
    embed = {
        "title": "⚠️ Alerte Bot Recrutement",
        "description": msg,
        "color": 0xE74C3C,  # Rouge
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{DISCORD_LOG_CHANNEL}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"},
            json={"embeds": [embed]},
            timeout=10
        )
    except Exception:
        pass

def notify_discord_round(poste_name: str, annonce_text: str, total_targets: int, success_count: int, error_count: int, next_run_dt):
    if not DISCORD_BOT_TOKEN or not DISCORD_LOG_CHANNEL:
        return
    embed = {
        "title": "📢 Annonce de Recrutement Publiée !",
        "description": "Une nouvelle tournée de publication automatique vient d'être envoyée avec succès sur Telegram.",
        "color": 0x3498DB,  # Bleu
        "fields": [
            {"name": "🎯 Poste ciblé", "value": f"**{poste_name}**", "inline": True},
            {"name": "📊 Bilan d'envoi", "value": f"✅ **{success_count}** envoyés · ⚠️ **{error_count}** ignorés (sur {total_targets} cibles)", "inline": True},
            {"name": "⏱️ Prochaine tournée", "value": f"Dans 20 minutes (à **{next_run_dt.strftime('%H:%M:%S')}**)", "inline": False},
            {"name": "📝 Texte publié (Aperçu)", "value": f"```{annonce_text[:850]}```", "inline": False}
        ],
        "footer": {"text": "AVA Agency — Bot Recrutement Telethon • Salon #log-rcrutement"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        requests.post(
            f"https://discord.com/api/v10/channels/{DISCORD_LOG_CHANNEL}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"},
            json={"embeds": [embed]},
            timeout=10
        )
        log.info("🔔 Notification envoyée sur Discord dans #log-rcrutement.")
    except Exception as e:
        log.warning(f"Erreur notification Discord tournée : {e}")

# ─── Tournée de publication dans les groupes ─────────────────────────────────
async def publish_round(client: TelegramClient, poste_name: str, annonce: str, target_groups: list[str]):
    if not annonce or not target_groups:
        log.warning("⚠️ Aucune annonce ou aucun groupe disponible.")
        return 0, 0

    log.info(f"📢 Début tournée [{poste_name}] vers {len(target_groups)} groupe(s)...")

    # Notification Discord immédiate du début de tournée
    notify_discord_round_start(poste_name, len(target_groups), annonce)

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
    return succes, erreurs

# ─── Boucle principale (20 minutes fixes) ────────────────────────────────────
async def main_loop():
    target_groups = load_target_groups()

    log.info("=" * 65)
    log.info("🚀 AVA Agency — Bot Recrutement Telethon (20 min fixes)")
    log.info(f"   Compte         : {PHONE_NUMBER}")
    log.info(f"   Groupes cibles : {len(target_groups)} groupes chargés")
    log.info(f"   Intervalle     : {POST_INTERVAL}s (20 minutes fixes)")
    log.info(f"   Mode           : 6 Modèles Officiels (5 VA + 1 Chatter) en Rotation Aléatoire")
    log.info(f"   Contact        : @rcruting_bot")
    log.info("=" * 65)

    client = init_telethon_client()
    await client.connect()

    if not await client.is_user_authorized():
        log.critical("❌ Le compte Telegram n'est PAS autorisé ou la session est expirée !")
        notify_discord_error("❌ Le compte Telegram n'est pas autorisé ou la session est expirée. Vérifiez recruiter.session.")
        await asyncio.sleep(60)
        return

    me = await client.get_me()
    me_title = me.first_name or "Compte Recrutement"
    log.info(f"✅ Connecté en tant que : {me_title} (@{me.username or 'sans_username'}, Tel: +{me.phone})")

    # Notification Discord au démarrage
    notify_discord_startup(PHONE_NUMBER, me_title, len(target_groups))

    while True:
        now = datetime.now()

        # Sélection aléatoire de l'un des 5 modèles officiels VA
        template_obj = get_next_random_template()
        poste_name = template_obj["poste"]
        annonce = template_obj["texte"]

        # Envoi de la tournée
        succes, erreurs = await publish_round(
            client, poste_name, annonce, target_groups
        )

        # ⏱️ Pause de 20 minutes fixes (1200 secondes)
        next_run = now + timedelta(seconds=POST_INTERVAL)

        # Notifier Discord avec l'aperçu du texte et le bilan d'envoi
        notify_discord_round(poste_name, annonce, len(target_groups), succes, erreurs, next_run)

        wait_seconds = max(10, (next_run - datetime.now()).total_seconds())
        log.info(f"😴 Prochaine tournée dans 20 minutes (à {next_run.strftime('%H:%M:%S')})")
        await asyncio.sleep(wait_seconds)

async def main():
    while True:
        try:
            await main_loop()
        except Exception as e:
            log.error(f"💥 Erreur main_loop: {e} — reprise dans 30s...")
            await asyncio.sleep(30)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Arrêté.")
