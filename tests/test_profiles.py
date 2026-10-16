import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from morse_art import DATA_DIR, SOURCE_PATHS, load_profile, prepare_profile


class ProfileTests(unittest.TestCase):
    def test_all_bundled_profiles_are_measured_attributed_and_usable(self):
        for key in SOURCE_PATHS:
            with self.subTest(key=key):
                profile = load_profile(key)
                self.assertEqual(len(profile.phase), 1024)
                self.assertEqual(profile.provenance["license"], "CC BY 4.0")
                self.assertEqual(len(profile.provenance["sha256"]), 64)
                self.assertIn("Pilia", profile.provenance["citation"])
                x, y = prepare_profile(profile)
                self.assertTrue(np.all(np.diff(x) > 0))
                self.assertTrue(np.isfinite(y).all())
                self.assertGreater(y.max(), 0.9)
                self.assertEqual(y[0], 0)
                self.assertEqual(y[-1], 0)
                self.assertTrue(np.all(y >= 0))

    def test_unknown_and_missing_sources_fail(self):
        with self.assertRaisesRegex(ValueError, "Unknown source"):
            load_profile("unknown")
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(FileNotFoundError):
            load_profile("b1919-hba", Path(directory))

    def test_invalid_profile_data_is_rejected(self):
        original = json.loads((DATA_DIR / "b1919-hba.json").read_text())
        variants = [
            {"hdr": {}},
            {**original, "series": {"I": [[0, 1], [0, 2]]}},
            {**original, "hdr": {**original["hdr"], "license": "unknown"}},
            {**original, "series": {"I": [[i, float("nan")] for i in range(20)]}},
            {**original, "series": {"I": [[i, 1] for i in range(20)]}},
        ]
        for data in variants:
            with self.subTest(data=str(data)[:80]), tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "b1919-hba.json").write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_profile("b1919-hba", Path(directory))


if __name__ == "__main__":
    unittest.main()
