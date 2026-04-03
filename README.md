# bot-random

Minimal Kriegspiel random-move bot.

## What it does

- registers with the Kriegspiel API
- authenticates with a bot bearer token
- polls assigned games
- can keep one open human-joinable lobby game advertised
- can also join another bot's waiting lobby game with 50% probability when one is available
- picks random kriegspiel-allowed moves exposed by the API
- keeps running through transient API failures

## Setup

Set `KRIEGSPIEL_BOT_OWNER_EMAIL` in `.env` before registering. The backend now requires it so Kriegspiel can contact the bot owner if needed.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py --register
python bot.py
```

By default the bot also keeps one open lobby game available for humans to join.
That behavior is controlled with:

- `KRIEGSPIEL_AUTO_CREATE_LOBBY_GAME=true|false`
- `KRIEGSPIEL_AUTO_CREATE_RULE_VARIANT=berkeley|berkeley_any`
- `KRIEGSPIEL_AUTO_CREATE_PLAY_AS=white|black|random`

Bot-vs-bot play is also enabled by default:

- the bot checks open waiting games
- it will only consider games created by another bot
- it will try to join one with 50% probability on a poll cycle
- it keeps a local one-minute cooldown between bot-vs-bot join attempts to match backend rules

## systemd

A production host can run the bot as a service with `deploy/kriegspiel-random-bot.service`.
