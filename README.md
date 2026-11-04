# ava-recruitment-bot

Bot Telegram de recrutement avec génération d'annonces par IA.

## Fonctionnalités
- Génère **3 à 5 annonces variées** au démarrage via **Gemini API** (fallback: **Groq**)
- Les publie en **rotation** dans les groupes Telegram configurés
- Publication toutes les **heures** (heure pile)
- Reconnexion automatique infinie sur Railway 24/7

## Flux IA
```
Gemini 1.5 Flash → (si échec) → Groq Llama3 → (si échec) → Annonce statique de base
```

## Variables d'environnement Railway
| Variable | Description | Exemple |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Token du bot Telegram | `123456:ABC...` |
| `TARGET_GROUPS` | IDs groupes (virgule) | `-1001234,-1005678` |
| `POST_INTERVAL` | Intervalle secondes | `3600` |
| `NB_ANNONCES` | Nb annonces IA | `5` |
| `GEMINI_API_KEY` | Clé Google AI Studio | `AIza...` |
| `GROQ_API_KEY` | Clé Groq (fallback) | `gsk_...` |

## Déploiement Railway
1. Créer un nouveau projet Railway
2. Connecter ce repo GitHub
3. Configurer les variables d'env ci-dessus
4. Railway détecte automatiquement le `Procfile` et démarre
