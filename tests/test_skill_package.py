"""Packaging checks only; these do not prove agent routing behavior."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1] / 'skills' / 'agent-workflow'


class SkillPackageTests(unittest.TestCase):
    def test_copied_skill_contains_resolvable_references_and_template(self):
        with tempfile.TemporaryDirectory() as temp:
            installed = Path(temp) / 'agent-workflow'
            shutil.copytree(SKILL, installed)
            for source in installed.rglob('*.md'):
                for target in re.findall(r'\]\(([^)]+)\)', source.read_text()):
                    if '://' in target or target.startswith('#'):
                        continue
                    resolved = (source.parent / target.split('#', 1)[0]).resolve()
                    with self.subTest(source=source.name, target=target):
                        self.assertTrue(resolved.is_relative_to(installed.resolve()))
                        self.assertTrue(resolved.is_file())
            config = json.loads(
                (installed / 'references' / 'routing.example.json').read_text())
            self.assertEqual(set(config['roles']), {
                'lookup', 'explore', 'implement', 'plan', 'debug', 'complex', 'review'})
            self.assertEqual(len(config['models']), 1)
            for alias in config['roles'].values():
                self.assertIn(alias, config['models'])
                self.assertEqual(config['models'][alias], {
                    'provider': 'host', 'model': 'inherit'})
            self.assertFalse((installed / 'models.json').exists())

    def test_stats_skill_is_user_invoked_and_runs_the_panel(self):
        text = (SKILL.parent / 'agent-workflow-stats' / 'SKILL.md').read_text()
        header = text.split('---')[1]
        self.assertIn('name: agent-workflow-stats', header)
        self.assertIn('disable-model-invocation: true', header)
        self.assertIn('allowed-tools: Bash(agent-run stats:*)', header)
        self.assertIn('!`agent-run stats --panel $ARGUMENTS`', text)
        self.assertRegex(header.split('name: ')[1].split()[0], r'^[a-z0-9-]+$')


if __name__ == '__main__':
    unittest.main()
