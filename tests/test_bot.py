from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import bot


class BotTests(unittest.TestCase):
    def tearDown(self) -> None:
        bot.configure_runtime_paths()

    def test_runtime_paths_isolate_instance_env_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env_path = temp_path / "randobot.env"
            state_path = temp_path / "state" / "randobot.json"
            env_path.write_text("KRIEGSPIEL_BOT_USERNAME=randobot2\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                bot.configure_runtime_paths(env_path=env_path, state_path=state_path)
                bot.load_env_file()
                bot.save_token("token-1")

                self.assertEqual(os.environ["KRIEGSPIEL_BOT_USERNAME"], "randobot2")
                self.assertEqual(state_path.read_text(encoding="utf-8").count("token-1"), 1)

    def test_under_active_game_limit_caps_parallel_games_at_ten(self) -> None:
        self.assertTrue(bot.under_active_game_limit([{"state": "active"}] * 9))
        self.assertFalse(bot.under_active_game_limit([{"state": "active"}] * 10))

    def test_active_game_discovery_limit_parses_default_and_custom_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bot.active_game_discovery_limit(), 100)
        with patch.dict(os.environ, {"KRIEGSPIEL_ACTIVE_GAME_DISCOVERY_LIMIT": "40"}):
            self.assertEqual(bot.active_game_discovery_limit(), 40)
        with patch.dict(os.environ, {"KRIEGSPIEL_ACTIVE_GAME_DISCOVERY_LIMIT": "0"}):
            self.assertEqual(bot.active_game_discovery_limit(), 1)
        with patch.dict(os.environ, {"KRIEGSPIEL_ACTIVE_GAME_DISCOVERY_LIMIT": "250"}):
            self.assertEqual(bot.active_game_discovery_limit(), 100)
        with patch.dict(os.environ, {"KRIEGSPIEL_ACTIVE_GAME_DISCOVERY_LIMIT": "invalid"}):
            self.assertEqual(bot.active_game_discovery_limit(), 100)

    def test_maybe_play_game_retries_moves_with_delay_until_one_succeeds(self) -> None:
        state = {
            "state": "active",
            "turn": "white",
            "your_color": "white",
            "possible_actions": ["move", "ask_any"],
            "allowed_moves": ["e2e4", "d2d4", "g1f3"],
        }
        posts: list[tuple[str, dict | None]] = []
        results = [
            {"announcement": "Illegal move", "move_done": False},
            {"announcement": "Move complete", "move_done": True},
        ]

        def fake_post_json(path: str, payload: dict | None = None) -> dict:
            posts.append((path, payload))
            return results.pop(0)

        with patch.object(bot, "get_json", return_value=state):
            with patch.object(bot, "choose_random_moves", return_value=["d2d4", "e2e4", "g1f3"]):
                with patch.object(bot, "post_json", side_effect=fake_post_json):
                    with patch.object(bot.time, "sleep") as sleep_mock:
                        self.assertTrue(bot.maybe_play_game("game-1"))

        self.assertEqual(
            posts,
            [
                ("/game/game-1/move", {"uci": "d2d4"}),
                ("/game/game-1/move", {"uci": "e2e4"}),
            ],
        )
        sleep_mock.assert_called_once_with(bot.FAILED_MOVE_RETRY_DELAY_SECONDS)

    def test_maybe_play_game_falls_back_to_ask_any_when_move_unavailable(self) -> None:
        state = {
            "state": "active",
            "turn": "white",
            "your_color": "white",
            "possible_actions": ["ask_any"],
            "allowed_moves": [],
        }

        with patch.object(bot, "get_json", return_value=state):
            with patch.object(bot, "post_json", return_value={"announcement": "No pawn captures."}) as post_json:
                self.assertFalse(bot.maybe_play_game("game-1"))

        post_json.assert_called_once_with("/game/game-1/ask-any")

    def test_open_bot_lobby_candidates_only_include_other_bot_waiting_games(self) -> None:
        with patch.dict("os.environ", {"KRIEGSPIEL_BOT_USERNAME": "randobot"}):
            candidates = bot.open_bot_lobby_candidates(
                [
                    {
                        "game_code": "BOT123",
                        "created_by": "gptnano",
                        "rule_variant": "berkeley_any",
                    },
                    {
                        "game_code": "SELF12",
                        "created_by": "randobot",
                        "rule_variant": "berkeley_any",
                    },
                    {
                        "game_code": "HUM123",
                        "created_by": "fil",
                        "rule_variant": "berkeley_any",
                    },
                ],
                profile_lookup=lambda username: {"role": "bot" if username == "gptnano" else "user"},
            )

        self.assertEqual([game["game_code"] for game in candidates], ["BOT123"])

    def test_open_bot_lobby_candidates_respect_supported_rule_variants(self) -> None:
        with patch.dict(
            "os.environ",
            {"KRIEGSPIEL_BOT_USERNAME": "randobot", "KRIEGSPIEL_SUPPORTED_RULE_VARIANTS": "berkeley,cincinnati,wild16,crazykrieg"},
        ):
            candidates = bot.open_bot_lobby_candidates(
                [
                    {"game_code": "BER123", "created_by": "gptnano", "rule_variant": "berkeley"},
                    {"game_code": "ANY123", "created_by": "gptnano", "rule_variant": "berkeley_any"},
                    {"game_code": "CIN123", "created_by": "gptnano", "rule_variant": "cincinnati"},
                    {"game_code": "WLD123", "created_by": "gptnano", "rule_variant": "wild16"},
                    {"game_code": "CRZ123", "created_by": "gptnano", "rule_variant": "crazykrieg"},
                ],
                profile_lookup=lambda username: {"role": "bot"},
            )

        self.assertEqual([game["game_code"] for game in candidates], ["BER123", "CIN123", "WLD123", "CRZ123"])

    def test_supported_rule_variants_default_to_all_supported_rulesets(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                bot.supported_rule_variants(),
                ["berkeley", "berkeley_any", "cincinnati", "wild16", "rand", "english", "crazykrieg"],
            )

    def test_supported_rule_variants_dedupe_and_ignore_unknown_rulesets(self) -> None:
        with patch.dict(
            "os.environ",
            {"KRIEGSPIEL_SUPPORTED_RULE_VARIANTS": "wild16,standard,cincinnati,wild16,berkeley_any"},
        ):
            self.assertEqual(bot.supported_rule_variants(), ["wild16", "cincinnati", "berkeley_any"])

    def test_create_payload_accepts_new_rule_variants(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "KRIEGSPIEL_SUPPORTED_RULE_VARIANTS": "berkeley,cincinnati,wild16,rand,english,crazykrieg",
                "KRIEGSPIEL_AUTO_CREATE_RULE_VARIANT": "crazykrieg",
            },
        ):
            self.assertEqual(bot.create_payload()["rule_variant"], "crazykrieg")

    def test_create_payload_falls_back_to_supported_rule_variant(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "KRIEGSPIEL_SUPPORTED_RULE_VARIANTS": "wild16",
                "KRIEGSPIEL_AUTO_CREATE_RULE_VARIANT": "standard",
            },
        ):
            self.assertEqual(bot.create_payload()["rule_variant"], "wild16")

    def test_register_bot_advertises_all_supported_rulesets_by_default(self) -> None:
        posts: list[dict] = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"api_token": "token-123"}

        def fake_post(*args, **kwargs):
            posts.append(kwargs)
            return FakeResponse()

        env = {
            "KRIEGSPIEL_API_BASE": "https://api.example.test",
            "KRIEGSPIEL_BOT_USERNAME": "randobot",
            "KRIEGSPIEL_BOT_DISPLAY_NAME": "Random Bot",
            "KRIEGSPIEL_BOT_OWNER_EMAIL": "bots@example.test",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(bot, "STATE_PATH", Path(temp_dir) / ".bot-state.json"):
                with patch.dict("os.environ", env, clear=True):
                    with patch.object(bot.requests, "post", side_effect=fake_post):
                        bot.register_bot()

        self.assertEqual(
            posts[0]["json"]["supported_rule_variants"],
            ["berkeley", "berkeley_any", "cincinnati", "wild16", "rand", "english", "crazykrieg"],
        )
        self.assertNotIn("headers", posts[0])

    def test_choose_bot_game_to_join_returns_candidate(self) -> None:
        games = [{"game_code": "BOT123", "created_by": "gptnano", "rule_variant": "berkeley_any"}]

        with patch.dict("os.environ", {"KRIEGSPIEL_BOT_USERNAME": "randobot"}):
            with patch.object(bot.random, "choice", side_effect=lambda items: items[0]):
                with patch.object(bot, "get_public_user", return_value={"role": "bot"}):
                    self.assertEqual(bot.choose_bot_game_to_join(games, rng=bot.random)["game_code"], "BOT123")

    def test_maybe_join_bot_lobby_game_records_attempt_even_when_probability_misses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / ".bot-state.json"
            open_games = {"games": [{"game_code": "BOT123", "created_by": "gptnano", "rule_variant": "berkeley_any"}]}
            with patch.object(bot, "STATE_PATH", state_path):
                with patch.dict("os.environ", {"KRIEGSPIEL_BOT_USERNAME": "randobot"}):
                    with patch.object(bot, "get_json", return_value=open_games):
                        with patch.object(bot, "get_public_user", return_value={"role": "bot"}):
                            with patch.object(bot.random, "choice", side_effect=lambda items: items[0]):
                                with patch.object(bot.random, "random", return_value=0.9):
                                    with patch.object(bot.time, "time", return_value=400.0):
                                        with patch.object(bot, "post_json") as post_mock:
                                            self.assertFalse(bot.maybe_join_bot_lobby_game(rng=bot.random))

                self.assertFalse(bot.can_attempt_bot_join(now=699.0))
                self.assertTrue(bot.can_attempt_bot_join(now=700.0))
                post_mock.assert_not_called()

    def test_maybe_join_bot_lobby_game_records_sample_even_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / ".bot-state.json"

            def fake_get_json(path: str) -> dict:
                if path == "/game/mine/active":
                    return {"games": []}
                if path == "/game/open":
                    return {"games": []}
                raise AssertionError(path)

            with patch.object(bot, "STATE_PATH", state_path):
                with patch.object(bot, "get_json", side_effect=fake_get_json):
                    with patch.object(bot.time, "time", return_value=400.0):
                        with patch.object(bot, "post_json") as post_mock:
                            self.assertFalse(bot.maybe_join_bot_lobby_game())

                self.assertFalse(bot.can_attempt_bot_join(now=699.0))
                self.assertTrue(bot.can_attempt_bot_join(now=700.0))
                post_mock.assert_not_called()

    def test_maybe_join_bot_lobby_game_skips_open_sample_during_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / ".bot-state.json"
            calls: list[str] = []

            def fake_get_json(path: str) -> dict:
                calls.append(path)
                raise AssertionError(path)

            with patch.object(bot, "STATE_PATH", state_path):
                bot.record_bot_join_attempt(now=100.0)
                with patch.object(bot, "get_json", side_effect=fake_get_json):
                    with patch.object(bot.time, "time", return_value=130.0):
                        self.assertFalse(bot.maybe_join_bot_lobby_game())

            self.assertEqual(calls, [])

    def test_maybe_join_bot_lobby_game_respects_active_game_limit(self) -> None:
        mine = {"games": [{"state": "active"}] * 10}

        def fake_get_json(path: str) -> dict:
            if path == "/game/mine/active":
                return mine
            raise AssertionError(path)

        with patch.object(bot, "get_json", side_effect=fake_get_json):
            with patch.object(bot, "post_json") as post_mock:
                self.assertFalse(bot.maybe_join_bot_lobby_game())

        post_mock.assert_not_called()

    def test_can_attempt_bot_join_uses_local_cooldown_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / ".bot-state.json"
            with patch.object(bot, "STATE_PATH", state_path):
                bot.record_bot_join_attempt(now=100.0)
                self.assertFalse(bot.can_attempt_bot_join(now=399.0))
                self.assertTrue(bot.can_attempt_bot_join(now=400.0))

    def test_has_own_waiting_game_detects_existing_lobby(self) -> None:
        with patch.dict("os.environ", {"KRIEGSPIEL_BOT_USERNAME": "randobot"}):
            self.assertTrue(bot.has_own_waiting_game([{"game_code": "ABC123", "created_by": "randobot"}]))
            self.assertFalse(bot.has_own_waiting_game([{"game_code": "XYZ789", "created_by": "gptnano"}]))

    def test_runner_scheduler_starts_one_runner_per_game_without_duplicates(self) -> None:
        class FakeRunner:
            def __init__(self, game_id: str) -> None:
                self.game_id = game_id
                self.started = 0
                self.stopped = 0
                self.joined = 0
                self.alive = False

            def start(self) -> None:
                self.started += 1
                self.alive = True

            def stop(self) -> None:
                self.stopped += 1
                self.alive = False

            def join(self, timeout: float | None = None) -> None:  # noqa: ARG002
                self.joined += 1

            def is_alive(self) -> bool:
                return self.alive

        created: dict[str, FakeRunner] = {}

        def runner_factory(game_id: str) -> FakeRunner:
            runner = FakeRunner(game_id)
            created[game_id] = runner
            return runner

        scheduler = bot.GameRunnerScheduler(poll_seconds=0.01, runner_factory=runner_factory)
        games = [
            {"state": "active", "game_id": "g1"},
            {"state": "active", "game_id": "g2"},
            {"state": "waiting", "game_id": "w1"},
        ]

        scheduler.reconcile(games)
        scheduler.reconcile(games)

        self.assertEqual(set(created), {"g1", "g2"})
        self.assertEqual(created["g1"].started, 1)
        self.assertEqual(created["g2"].started, 1)

        scheduler.reconcile([{"state": "active", "game_id": "g2"}])

        self.assertEqual(created["g1"].stopped, 0)
        self.assertIn("g1", scheduler.runners)
        self.assertIn("g2", scheduler.runners)

        created["g1"].alive = False
        scheduler.reconcile([{"state": "active", "game_id": "g2"}])

        self.assertNotIn("g1", scheduler.runners)
        self.assertIn("g2", scheduler.runners)

    def test_one_slow_game_runner_does_not_block_another_runner(self) -> None:
        slow_started = threading.Event()
        release_slow = threading.Event()
        fast_played = threading.Event()

        def fake_get_json(path: str) -> dict[str, str]:
            game_id = path.split("/")[2]
            return {"state": "active", "turn": "white", "your_color": "white", "game_id": game_id}

        def fake_maybe_play_game(game_id: str) -> bool:
            if game_id == "slow":
                slow_started.set()
                release_slow.wait(timeout=1)
                return True
            fast_played.set()
            return True

        slow_runner = bot.GameRunner("slow", poll_seconds=0.01)
        fast_runner = bot.GameRunner("fast", poll_seconds=0.01)

        with patch.object(bot, "get_json", side_effect=fake_get_json):
            with patch.object(bot, "maybe_play_game", side_effect=fake_maybe_play_game):
                slow_runner.start()
                self.assertTrue(slow_started.wait(timeout=0.5))
                fast_runner.start()
                self.assertTrue(fast_played.wait(timeout=0.5))
                slow_runner.stop()
                fast_runner.stop()
                release_slow.set()
                slow_runner.join(timeout=1)
                fast_runner.join(timeout=1)

        self.assertFalse(slow_runner.is_alive())
        self.assertFalse(fast_runner.is_alive())


if __name__ == "__main__":
    unittest.main()
