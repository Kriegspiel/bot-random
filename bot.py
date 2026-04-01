"""Reference implementation of a very small Kriegspiel bot.

This bot deliberately keeps the policy simple: whenever it is the bot's turn,
it fetches the current private game state, shuffles the legal UCI moves the API
already exposed to that player, and submits them one by one until one sticks.
If no common move completes a turn, it falls back to the "ask any captures?"
question when the server says that action is available.

The file is intentionally well-commented because this repository doubles as
example code for future bot authors.
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / ".bot-state.json"
ENV_PATH = BASE_DIR / ".env"
DEFAULT_TIMEOUT_SECONDS = 20


def load_env_file(path: str | Path = ENV_PATH) -> None:
    """Load simple KEY=VALUE pairs from a local .env file if it exists."""

    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def base_url() -> str:
    """Return the API base URL without a trailing slash."""

    return os.environ.get("KRIEGSPIEL_API_BASE", "http://localhost:8000").rstrip("/")


def auth_headers() -> dict[str, str]:
    """Build bearer auth headers from the bot token in the environment."""

    token = os.environ.get("KRIEGSPIEL_BOT_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def save_token(token: str) -> None:
    """Persist a newly-issued bot token locally for later runs."""

    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    state["token"] = token
    STATE_PATH.write_text(json.dumps(state, indent=2))


def maybe_restore_token() -> None:
    """Restore a previously saved token when the environment is empty."""

    if os.environ.get("KRIEGSPIEL_BOT_TOKEN"):
        return
    if STATE_PATH.exists():
        token = json.loads(STATE_PATH.read_text()).get("token")
        if token:
            os.environ["KRIEGSPIEL_BOT_TOKEN"] = token


def register_bot() -> None:
    """Register the bot account and store the returned API token."""

    response = requests.post(
        f"{base_url()}/api/auth/bots/register",
        headers={"X-Bot-Registration-Key": os.environ["KRIEGSPIEL_BOT_REGISTRATION_KEY"]},
        json={
            "username": os.environ["KRIEGSPIEL_BOT_USERNAME"],
            "display_name": os.environ["KRIEGSPIEL_BOT_DISPLAY_NAME"],
            "owner_email": os.environ["KRIEGSPIEL_BOT_OWNER_EMAIL"],
            "description": os.environ.get("KRIEGSPIEL_BOT_DESCRIPTION", ""),
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    save_token(payload["api_token"])
    print(json.dumps(payload, indent=2))


def get_json(path: str) -> dict:
    """GET a JSON API endpoint and raise for non-success responses."""

    response = requests.get(f"{base_url()}{path}", headers=auth_headers(), timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def post_json(path: str, payload: dict | None = None) -> dict:
    """POST JSON to the API and return the decoded payload."""

    response = requests.post(
        f"{base_url()}{path}",
        headers=auth_headers(),
        json=payload or {},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def choose_random_moves(allowed_moves: list[str]) -> list[str]:
    """Return the server-provided legal moves in random order.

    The backend already filtered the move list to this player's currently legal
    possibilities, so the bot only randomizes ordering.
    """

    moves = list(allowed_moves)
    random.shuffle(moves)
    return moves


def maybe_play_game(game_id: str) -> bool:
    """Play one turn in the specified game if it is currently ours."""

    state = get_json(f"/api/game/{game_id}/state")
    if state.get("state") != "active" or state.get("turn") != state.get("your_color"):
        return False
    if "move" not in state.get("possible_actions", []):
        return False

    # Try common moves first. We optimistically walk the shuffled legal list;
    # the API remains the source of truth and will reject anything stale.
    for uci in choose_random_moves(state.get("allowed_moves", [])):
        result = post_json(f"/api/game/{game_id}/move", {"uci": uci})
        print(f"{game_id}: tried {uci} -> {result['announcement']}")
        if result.get("move_done"):
            return True

    # If no move completed a turn, use the alternate question flow when offered.
    if "ask_any" in state.get("possible_actions", []):
        result = post_json(f"/api/game/{game_id}/ask-any")
        print(f"{game_id}: ask-any -> {result['announcement']}")
    return False


def run_loop(poll_seconds: float) -> None:
    """Poll the bot's games forever and act whenever a turn is available."""

    while True:
        try:
            mine = get_json("/api/game/mine")
            for game in mine.get("games", []):
                if game.get("state") == "active":
                    maybe_play_game(game["game_id"])
        except requests.RequestException as exc:
            print(f"poll failed: {exc}", file=sys.stderr, flush=True)
        time.sleep(poll_seconds)


def main() -> None:
    load_env_file()
    maybe_restore_token()

    parser = argparse.ArgumentParser(description="Run the reference Kriegspiel random bot.")
    parser.add_argument("--register", action="store_true", help="Register the bot and persist the returned token.")
    parser.add_argument("--poll-seconds", type=float, default=3.0, help="Seconds between /api/game/mine polls.")
    args = parser.parse_args()

    if args.register:
        register_bot()
        return

    if not os.environ.get("KRIEGSPIEL_BOT_TOKEN"):
        raise SystemExit("KRIEGSPIEL_BOT_TOKEN is missing. Run with --register first.")

    run_loop(args.poll_seconds)


if __name__ == "__main__":
    main()
