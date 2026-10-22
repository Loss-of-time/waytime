"""Unit tests for waytime_core (no D-Bus or KWin needed)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import waytime_core as core  # noqa: E402


class LimitConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.toml")

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        limits = [
            core.Limit("steam", 90, (15, 5, 1), "close"),
            core.Limit("org.kde.dolphin", 20, (10,), "kill"),
        ]
        core.save_limits(limits, self.path)
        loaded = core.load_limits(self.path)
        self.assertEqual(loaded, limits)

    def test_missing_file_means_no_limits(self):
        self.assertEqual(core.load_limits(self.path), [])

    def test_malformed_toml_means_no_limits(self):
        with open(self.path, "w") as fh:
            fh.write("[[limits]\napp = ")
        self.assertEqual(core.load_limits(self.path), [])

    def test_invalid_entries_are_skipped_and_action_defaults(self):
        with open(self.path, "w") as fh:
            fh.write(
                """
[[limits]]
app = "steam"
minutes = 60
action = "nonsense"

[[limits]]
app = ""
minutes = 30

[[limits]]
app = "discord"
minutes = 0

[[limits]]
minutes = 45
"""
            )
        loaded = core.load_limits(self.path)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].app, "steam")
        self.assertEqual(loaded[0].action, "close")
        self.assertEqual(loaded[0].warn_minutes, core.DEFAULT_WARN_MINUTES)

    def test_warn_minutes_are_sanitized(self):
        with open(self.path, "w") as fh:
            fh.write(
                """
[[limits]]
app = "mpv"
minutes = 30
warn_minutes = [5, 5, -1, "x", 10]
"""
            )
        loaded = core.load_limits(self.path)
        self.assertEqual(loaded[0].warn_minutes, (10, 5))

    def test_find_limit_is_case_insensitive(self):
        limits = [core.Limit("Steam", 60)]
        self.assertIsNotNone(core.find_limit(limits, "steam"))
        self.assertIsNotNone(core.find_limit(limits, "  STEAM "))
        self.assertIsNone(core.find_limit(limits, "discord"))


class EvaluationTests(unittest.TestCase):
    def test_remaining_and_exhausted(self):
        limit = core.Limit("steam", 10)
        self.assertEqual(core.remaining_seconds(limit, 0), 600)
        self.assertFalse(core.is_exhausted(limit, 599))
        self.assertTrue(core.is_exhausted(limit, 600))

    def test_warning_fires_once_per_threshold(self):
        limit = core.Limit("steam", 90, (15, 5, 1))
        fired = set()

        self.assertEqual(core.due_warning(limit, 15 * 60 - 1, fired), 15)
        self.assertEqual(fired, {15})
        self.assertIsNone(core.due_warning(limit, 14 * 60, fired))

        self.assertEqual(core.due_warning(limit, 5 * 60 - 1, fired), 5)
        self.assertEqual(fired, {15, 5})

        self.assertEqual(core.due_warning(limit, 60 - 1, fired), 1)
        self.assertIsNone(core.due_warning(limit, 0, fired))
        self.assertIsNone(core.due_warning(limit, -5, fired))

    def test_warning_jump_reports_most_urgent_and_marks_all(self):
        limit = core.Limit("steam", 90, (15, 5, 1))
        fired = set()
        # Daemon stalled: all three thresholds are already crossed.
        self.assertEqual(core.due_warning(limit, 30, fired), 1)
        self.assertEqual(fired, {15, 5, 1})

    def test_threshold_above_limit_never_fires(self):
        limit = core.Limit("steam", 10, (15, 5))
        fired = set()
        self.assertIsNone(core.due_warning(limit, 599, fired))
        self.assertEqual(core.due_warning(limit, 299, fired), 5)
        self.assertEqual(fired, {5})


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = core.Store(os.path.join(self.tmp.name, "test.db"))

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_usage_accumulates_per_date(self):
        self.store.add("steam", "", 30, date="2026-01-01")
        self.store.add("steam", "", 45, date="2026-01-01")
        self.store.add("steam", "", 10, date="2026-01-02")
        self.assertEqual(self.store.usage("steam", "2026-01-01"), 75)
        self.assertEqual(self.store.usage("steam", "2026-01-02"), 10)
        self.assertEqual(self.store.usage("unknown", "2026-01-01"), 0)

    def test_sites_are_stored_separately(self):
        self.store.add("firefox", "YouTube", 12, date="2026-01-01")
        row = self.store.db.execute(
            "SELECT seconds FROM sites WHERE date = ? AND site = ?",
            ("2026-01-01", "YouTube"),
        ).fetchone()
        self.assertEqual(row[0], 12)

    def test_events_are_logged(self):
        self.store.log_event("steam", "warn", "5m remaining")
        events = self.store.events()
        self.assertEqual(len(events), 1)
        _, app, kind, detail = events[0]
        self.assertEqual((app, kind, detail), ("steam", "warn", "5m remaining"))


class PrettyTests(unittest.TestCase):
    def test_pretty_app(self):
        self.assertEqual(core.pretty_app("org.kde.dolphin"), "Dolphin")
        self.assertEqual(core.pretty_app("steam"), "Steam")
        self.assertEqual(core.pretty_app("google-chrome"), "Google Chrome")


if __name__ == "__main__":
    unittest.main()
