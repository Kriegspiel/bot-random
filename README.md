# bot-random

Minimal Kriegspiel random-move bot.

## What it does

- registers with the Kriegspiel API
- authenticates with a bot bearer token
- polls assigned games
- picks random kriegspiel-allowed moves exposed by the API
- keeps running through transient API failures

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py --register
python bot.py
```

## systemd

A production host can run the bot as a service with `deploy/kriegspiel-random-bot.service`.
