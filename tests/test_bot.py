from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bot


class BotTests(unittest.TestCase):
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
        with patch.dict("os.environ", {"KRIEGSPIEL_BOT_USERNAME": "randobot", "KRIEGSPIEL_SUPPORTED_RULE_VARIANTS": "berkeley,berkeley_any"}):
            candidates = bot.open_bot_lobby_candidates(
                [
                    {"game_code": "BER123", "created_by": "gptnano", "rule_variant": "berkeley"},
                    {"game_code": "ANY123", "created_by": "gptnano", "rule_variant": "berkeley_any"},
                ],
                profile_lookup=lambda username: {"role": "bot"},
            )

        self.assertEqual([game["game_code"] for game in candidates], ["BER123", "ANY123"])

    def test_choose_bot_game_to_join_respects_probability(self) -> None:
        games = [{"game_code": "BOT123", "created_by": "gptnano", "rule_variant": "berkeley_any"}]

        with patch.dict("os.environ", {"KRIEGSPIEL_BOT_USERNAME": "randobot"}):
            with patch.object(bot.random, "random", return_value=0.9):
                self.assertIsNone(bot.choose_bot_game_to_join(games, rng=bot.random))
            with patch.object(bot.random, "random", return_value=0.1):
                with patch.object(bot.random, "choice", side_effect=lambda items: items[0]):
                    with patch.object(bot, "get_public_user", return_value={"role": "bot"}):
                        self.assertEqual(bot.choose_bot_game_to_join(games, rng=bot.random)["game_code"], "BOT123")

    def test_can_attempt_bot_join_uses_local_cooldown_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / ".bot-state.json"
            with patch.object(bot, "STATE_PATH", state_path):
                bot.record_bot_join_attempt(now=100.0)
                self.assertFalse(bot.can_attempt_bot_join(now=120.0))
                self.assertTrue(bot.can_attempt_bot_join(now=161.0))

    def test_has_own_waiting_game_detects_existing_lobby(self) -> None:
        with patch.dict("os.environ", {"KRIEGSPIEL_BOT_USERNAME": "randobot"}):
            self.assertTrue(bot.has_own_waiting_game([{"game_code": "ABC123", "created_by": "randobot"}]))
            self.assertFalse(bot.has_own_waiting_game([{"game_code": "XYZ789", "created_by": "gptnano"}]))


if __name__ == "__main__":
    unittest.main()
