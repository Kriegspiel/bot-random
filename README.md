# ks-random-bot

Minimal Kriegspiel random-move bot.

## What it does

- registers with the Kriegspiel API
- authenticates with a bot bearer token
- polls assigned games
- picks random visible-board moves
- retries until one sticks

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py --register
python bot.py
```
