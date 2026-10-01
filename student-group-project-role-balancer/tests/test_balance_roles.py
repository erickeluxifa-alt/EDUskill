import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / 'scripts' / 'balance_roles.py'
SAMPLE = ROOT / 'examples' / 'sample_input.json'

class RoleBalancerTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)

    def test_demo_json_has_complete_groups(self):
        result = self.run_cli('--demo', '--json')
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload['groups']), 2)
        self.assertEqual(sum(len(g['members']) for g in payload['groups']), 6)
        self.assertTrue(all(len(g['members']) == 3 for g in payload['groups']))

    def test_files_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli('--input', str(SAMPLE), '--out-dir', directory)
            self.assertEqual(result.returncode, 0)
            self.assertTrue((Path(directory) / 'role_plan.json').exists())
            self.assertTrue((Path(directory) / 'role_plan.md').exists())

    def test_invalid_student_count_is_rejected(self):
        data = json.loads(SAMPLE.read_text())
        data['students'].pop()
        with tempfile.NamedTemporaryFile('w', suffix='.json') as f:
            json.dump(data, f)
            f.flush()
            result = self.run_cli('--input', f.name, '--strict', '--json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('学生人数', result.stderr)

    def test_strict_reports_warning(self):
        data = json.loads(SAMPLE.read_text())
        data['rules']['max_same_skill_in_group'] = 0
        with tempfile.NamedTemporaryFile('w', suffix='.json') as f:
            json.dump(data, f)
            f.flush()
            result = self.run_cli('--input', f.name, '--strict', '--json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('warnings', result.stdout)

if __name__ == '__main__':
    unittest.main()
