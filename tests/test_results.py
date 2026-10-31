"""Offline regression and negative-control tests for the published numbers."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_results", ROOT / "tools/check_results.py")
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PublishedResultsTests(unittest.TestCase):
    def test_full_saved_matrix_and_denominators(self):
        result = checker.verify(ROOT)
        self.assertEqual(result["matrix_cells_recomputed"], 60)
        self.assertEqual(result["qualified_requests"], 972)

    def test_fixed_window_crossings_and_short_output(self):
        self.assertEqual(checker.decode_rate({"events": [
            {"seconds": 1.0, "count": 130}, {"seconds": 3.0, "count": 645}]}), 256.0)
        self.assertIsNone(checker.decode_rate({"events": [{"seconds": 1.0, "count": 128}]}))

    def test_nonpositive_window_rejected(self):
        with self.assertRaises(ValueError):
            checker.decode_rate({"events": [{"seconds": 1.0, "count": 645}]})

    def test_tampered_aggregate_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="tp8-result-negative-") as tmp:
            destination = Path(tmp)
            shutil.copytree(ROOT / "results", destination / "results")
            table = destination / "results/matrix.csv"
            rows = table.read_text().splitlines()
            header = rows[0].split(",")
            fields = rows[1].split(",")
            fields[header.index("median_aggregate_e2e_tps")] = "999999"
            rows[1] = ",".join(fields)
            table.write_text("\n".join(rows) + "\n")
            with self.assertRaises(ValueError):
                checker.verify(destination)


if __name__ == "__main__":
    unittest.main()
