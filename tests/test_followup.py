"""Offline denominator and corruption checks for the follow-up data export."""
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_followup', ROOT / 'tools/check_followup.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class FollowupTests(unittest.TestCase):
    def test_committed_outcomes_and_counts(self):
        result = checker.verify(ROOT)
        self.assertEqual(result['counts']['c16_timed_responses'], 1280)
        self.assertEqual(result['counts']['fleet_background_passed'], 240)
        self.assertEqual(result['counts']['fleet_foreground_passed'], 15)
        self.assertEqual(result, json.loads((ROOT / 'results/vllm-followup-summary.json').read_text()))

    def test_changed_native_output_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'results', root / 'results')
            path = root / 'results/vllm-followup-observations.json.gz'
            data = json.loads(gzip.decompress(path.read_bytes()))
            data['c16'][0]['native_output_tokens'] = 4097
            path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
            with self.assertRaises(AssertionError):
                checker.verify(root)

    def test_wrong_tool_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'results', root / 'results')
            path = root / 'results/vllm-followup-observations.json.gz'
            data = json.loads(gzip.decompress(path.read_bytes()))
            data['hermes_fleet'][0]['sessions'][0]['actual_state']['total'] += 1
            path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
            with self.assertRaises(AssertionError):
                checker.verify(root)


if __name__ == '__main__':
    unittest.main()
