import argparse
import json
import os
import random
import time
from pathlib import Path

import chess
import requests

STATE_PATH = Path('.bot-state.json')


def load_env_file(path: str = '.env'):
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


def base_url() -> str:
    return os.environ.get('KRIEGSPIEL_API_BASE', 'http://localhost:8000').rstrip('/')


def auth_headers() -> dict[str, str]:
    token = os.environ.get('KRIEGSPIEL_BOT_TOKEN', '').strip()
    return {'Authorization': f'Bearer {token}'} if token else {}


def save_token(token: str):
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    state['token'] = token
    STATE_PATH.write_text(json.dumps(state, indent=2))


def maybe_restore_token():
    if os.environ.get('KRIEGSPIEL_BOT_TOKEN'):
        return
    if STATE_PATH.exists():
        token = json.loads(STATE_PATH.read_text()).get('token')
        if token:
            os.environ['KRIEGSPIEL_BOT_TOKEN'] = token


def register_bot():
    response = requests.post(
        f"{base_url()}/api/auth/bots/register",
        headers={'X-Bot-Registration-Key': os.environ['KRIEGSPIEL_BOT_REGISTRATION_KEY']},
        json={
            'username': os.environ['KRIEGSPIEL_BOT_USERNAME'],
            'display_name': os.environ['KRIEGSPIEL_BOT_DISPLAY_NAME'],
            'description': os.environ.get('KRIEGSPIEL_BOT_DESCRIPTION', ''),
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    save_token(payload['api_token'])
    print(json.dumps(payload, indent=2))


def get_json(path: str):
    response = requests.get(f"{base_url()}{path}", headers=auth_headers(), timeout=20)
    response.raise_for_status()
    return response.json()


def post_json(path: str, payload: dict | None = None):
    response = requests.post(f"{base_url()}{path}", headers=auth_headers(), json=payload or {}, timeout=20)
    response.raise_for_status()
    return response.json()


def choose_random_moves(fen: str) -> list[str]:
    board = chess.Board(fen)
    moves = [move.uci() for move in board.legal_moves]
    random.shuffle(moves)
    return moves


def maybe_play_game(game_id: str):
    state = get_json(f'/api/game/{game_id}/state')
    if state.get('state') != 'active' or state.get('turn') != state.get('your_color'):
        return False
    if 'move' not in state.get('possible_actions', []):
        return False
    for uci in choose_random_moves(state['your_fen']):
        result = post_json(f'/api/game/{game_id}/move', {'uci': uci})
        print(f"{game_id}: tried {uci} -> {result['announcement']}")
        if result.get('move_done'):
            return True
    if 'ask_any' in state.get('possible_actions', []):
        result = post_json(f'/api/game/{game_id}/ask-any')
        print(f"{game_id}: ask-any -> {result['announcement']}")
    return False


def run_loop(poll_seconds: float):
    while True:
        mine = get_json('/api/game/mine')
        for game in mine.get('games', []):
            if game.get('state') == 'active':
                maybe_play_game(game['game_id'])
        time.sleep(poll_seconds)


def main():
    load_env_file()
    maybe_restore_token()
    parser = argparse.ArgumentParser()
    parser.add_argument('--register', action='store_true')
    parser.add_argument('--poll-seconds', type=float, default=3.0)
    args = parser.parse_args()
    if args.register:
        register_bot()
        return
    if not os.environ.get('KRIEGSPIEL_BOT_TOKEN'):
        raise SystemExit('KRIEGSPIEL_BOT_TOKEN is missing. Run with --register first.')
    run_loop(args.poll_seconds)


if __name__ == '__main__':
    main()
