import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from copy import deepcopy
from unittest.mock import patch

WORKFLOW_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = WORKFLOW_ROOT / 'examples'
EXAMPLE_CONFIG = WORKFLOW_ROOT / 'tests' / 'fixtures'
TEST_STATE = Path(tempfile.mkdtemp(prefix='agent-workflow-tests-'))
os.environ['AGENT_WORKFLOW_CONFIG'] = str(EXAMPLE_CONFIG)
os.environ['AGENT_WORKFLOW_STATE'] = str(TEST_STATE)
spec = importlib.util.spec_from_file_location('workflow', WORKFLOW_ROOT / 'agent_run.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def test_config_and_state_are_outside_source(self):
        self.assertEqual(w.CONFIG, EXAMPLE_CONFIG)
        self.assertEqual(w.STATE, TEST_STATE.resolve())
        self.assertFalse(w.STATE.is_relative_to(w.SOURCE_ROOT))

    def test_xdg_state_default_override_and_missing_config_error(self):
        with tempfile.TemporaryDirectory() as temp:
            env = os.environ.copy()
            env.pop('AGENT_WORKFLOW_CONFIG', None)
            env.pop('AGENT_WORKFLOW_STATE', None)
            env['XDG_CONFIG_HOME'] = str(Path(temp) / 'xdg with spaces')
            config_dir = Path(env['XDG_CONFIG_HOME']) / 'agent-workflow'
            config_dir.mkdir(parents=True)
            shutil.copyfile(EXAMPLE_CONFIG / 'models.json', config_dir / 'models.json')
            result = subprocess.run(
                [os.sys.executable, str(WORKFLOW_ROOT / 'agent_run.py'), 'remember',
                 '--repo', temp, '--text', 'xdg fact', '--source', 'test'],
                env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list((config_dir / 'state').rglob('MEMORY.md'))), 1)

            override_state = Path(temp) / 'state override with spaces'
            env['AGENT_WORKFLOW_STATE'] = str(override_state)
            result = subprocess.run(
                [os.sys.executable, str(WORKFLOW_ROOT / 'agent_run.py'), 'remember',
                 '--repo', temp, '--text', 'override fact', '--source', 'test'],
                env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(override_state.rglob('MEMORY.md'))), 1)

            env['XDG_CONFIG_HOME'] = str(Path(temp) / 'missing config')
            env.pop('AGENT_WORKFLOW_STATE')
            result = subprocess.run(
                [os.sys.executable, str(WORKFLOW_ROOT / 'agent_run.py'), 'run',
                 '--repo', temp, '--dry-run', 'test-1'],
                env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Workflow configuration is missing', result.stderr)

    def test_help_does_not_require_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, 'AGENT_WORKFLOW_CONFIG': str(Path(temp) / 'missing')}
            result = subprocess.run(
                [os.sys.executable, str(WORKFLOW_ROOT / 'agent_run.py'), '--help'],
                env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('usage:', result.stdout)

    def test_default_and_override_routing(self):
        self.assertEqual(w.select('implement')['model'], 'gpt-5.6-sol')
        self.assertEqual(w.select('implement', uncertainty='specified')['alias'], 'luna')
        self.assertEqual(w.select('implement', uncertainty='architectural')['alias'], 'astra')
        self.assertEqual(w.select('implement', override='opus-5.5',
                                  uncertainty='specified')['alias'], 'opus-5.5')
        self.assertEqual(w.select('review', after='opus-5.5')['alias'], 'astra')
        self.assertEqual(w.select('review', override='luna', after='opus-5.5')['alias'], 'luna')
        self.assertEqual(w.select('implement', escalate=True)['alias'], 'opus-5.5')
        with self.assertRaises(ValueError):
            w.select('implement', override='not-a-model')

    def test_arbitrary_aliases_single_provider_and_optional_routes(self):
        cfg = json.loads((EXAMPLES / 'models.json').read_text())
        with patch.object(w, 'config', return_value=cfg):
            self.assertEqual(w.select('implement', uncertainty='specified')['alias'], 'primary')
            self.assertEqual(w.select('review', after='primary')['alias'], 'primary')
            self.assertEqual(w.select('complex', escalate=True)['alias'], 'primary')

        routed = json.loads((EXAMPLES / 'models-routing.json').read_text())
        with patch.object(w, 'config', return_value=routed):
            self.assertEqual(w.select('implement', uncertainty='specified')['alias'], 'fast')
            self.assertEqual(w.select('implement', uncertainty='local')['alias'], 'deep')
            self.assertEqual(w.select('review', after='fast')['alias'], 'independent-review')
            self.assertEqual(w.select('review', after='independent-review')['alias'], 'deep')
            self.assertEqual(w.select('review', override='fast', after='missing')['alias'], 'fast')

    def test_single_provider_config_and_doctor_ignore_unused_binaries(self):
        for provider, unused in [('codex', 'claude'), ('claude', 'codex')]:
            cfg = json.loads((EXAMPLES / 'models.json').read_text())
            cfg['models']['primary']['provider'] = provider
            cfg['binaries'] = {provider: provider, 'ygg': 'ygg'}
            w._validate_config(cfg)
            cfg['binaries'][unused] = '/not-installed/unused-provider'
            result = types.SimpleNamespace(stdout='version', stderr='')
            with self.subTest(provider=provider), \
                    patch.object(w, 'config', return_value=cfg), \
                    patch.object(w, 'call', return_value=result) as invoke, \
                    patch.object(w, 'ygg', return_value=result), \
                    patch.object(w, 'project', return_value=(Path('/tmp'), Path('/tmp/state'))), \
                    patch.object(w.sys, 'argv', ['agent-run', 'doctor']), \
                    patch('builtins.print'):
                w.main()
                self.assertEqual({call.args[0][0] for call in invoke.call_args_list},
                                 {provider, 'ygg'})

    def test_malformed_routing_and_unknown_provider_are_rejected(self):
        base = json.loads((EXAMPLES / 'models.json').read_text())
        cases = []
        malformed = deepcopy(base)
        malformed['implementation_routes'] = []
        cases.append((malformed, 'implementation_routes must be an object'))
        malformed = deepcopy(base)
        malformed['implementation_routes'] = {'remote': 'primary'}
        cases.append((malformed, 'unsupported keys: remote'))
        malformed = deepcopy(base)
        malformed['review_routes'] = []
        cases.append((malformed, 'review_routes must be an object'))
        malformed = deepcopy(base)
        malformed['review_routes'] = {'codex': 'missing'}
        cases.append((malformed, 'unknown model alias'))
        malformed = deepcopy(base)
        malformed['models']['primary']['provider'] = 'custom'
        cases.append((malformed, 'provider must be one of'))
        for cfg, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                w._validate_config(cfg)

    def test_missing_policy_is_empty(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'CONFIG', Path(temp)):
            self.assertEqual(w.policy(), '')
            expected = '  personal policy\nwith trailing space  \n'
            Path(temp, 'AGENTS.md').write_text(expected)
            self.assertEqual(w.policy(), expected)

    def test_worker_restrictions(self):
        command = w.worker_command(w.select('lookup'), 'lookup', 'policy', Path('/tmp/result'))
        self.assertIn('read-only', command)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)
        command = w.worker_command(w.select('explore'), 'explore', 'policy', Path('/tmp/result'))
        self.assertEqual(command[command.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertEqual(command[command.index('--permission-mode') + 1], 'dontAsk')

    def test_management_launch_uses_configured_binary(self):
        cfg = deepcopy(w.config())
        cfg['binaries']['codex'] = '/custom path/codex'
        with patch.object(w, 'config', return_value=cfg), \
                patch.object(w.os, 'execvp', side_effect=SystemExit) as execute:
            with self.assertRaises(SystemExit):
                w.launch('codex', ['--version'])
            execute.assert_called_once_with('/custom path/codex',
                                            ['/custom path/codex', '--version'])

    def test_launch_rejects_unsupported_provider(self):
        with self.assertRaisesRegex(ValueError, 'Unknown provider'):
            w.launch('custom', [])

    def test_worktrees_share_memory_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            root.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init')
            git('-c', 'commit.gpgsign=false', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                'commit', '--allow-empty', '-m', 'test')
            other = Path(temp) / 'other'
            git('worktree', 'add', '-b', 'test', str(other))
            self.assertEqual(w.project(root)[1], w.project(other)[1])

    def test_task_guard_excludes_another_process(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp)):
            with w.guard('task:test'):
                with self.assertRaises(RuntimeError):
                    with w.guard('task:test'):
                        self.fail('Lock should be exclusive')
            with w.guard('task:test'):
                pass

    def test_notes_preserve_prior_handoff(self):
        with patch.object(w, 'show', return_value={'task': {'notes': 'prior'}}), patch.object(w, 'ygg') as ygg:
            w.append_notes('task-1', Path('/tmp'), 'next')
            self.assertEqual(ygg.call_args.args[0][-1], 'prior\n\nnext')

    def test_recursion_rejected(self):
        with patch.dict(os.environ, {'AGENT_WORKFLOW_WORKER': '1'}):
            with self.assertRaisesRegex(RuntimeError, 'recursion'):
                w.run_worker(None, Path('/tmp'))

    def test_startup_survives_database_outage(self):
        with patch.object(w, 'ygg', side_effect=RuntimeError('offline')):
            text = w.context(Path('/tmp'))
            self.assertIn('Active tasks unavailable', text)
            self.assertIn('Scoped learnings unavailable', text)

    def test_external_run_is_not_stolen(self):
        with patch.object(w, 'ygg', return_value=types.SimpleNamespace(stdout='#3  \x1b[32mrunning\x1b[0m ok')):
            with self.assertRaisesRegex(RuntimeError, 'active Yggdrasil run'):
                w.require_idle('test-1', Path('/tmp'))

    def test_packet_counts_utf8_and_rejects_overflow(self):
        task = {'ref': 'test-1', 'task': {'task_id': 'uuid', 'title': 'T',
                'description': 'snowman ☃', 'acceptance': 'done', 'notes': 'excluded'}}
        cfg = deepcopy(w.config())
        cfg['worker_packet_bytes'] = 100000
        with patch.object(w, 'config', return_value=cfg):
            prompt, size = w.build_worker_packet('implement', Path('/tmp'), task,
                                                 'assign ☃', Path('/tmp/run'), 'policy')
        self.assertEqual(size, len('policy'.encode()) + len(prompt.encode()))
        self.assertNotIn('excluded', prompt)
        cfg['worker_packet_bytes'] = size
        with patch.object(w, 'config', return_value=cfg):
            w.build_worker_packet('implement', Path('/tmp'), task, 'assign ☃',
                                  Path('/tmp/run'), 'policy')
        cfg['worker_packet_bytes'] = size - 1
        with patch.object(w, 'config', return_value=cfg), \
             self.assertRaisesRegex(RuntimeError, 'UTF-8 bytes'):
            w.build_worker_packet('implement', Path('/tmp'), task, 'assign ☃',
                                  Path('/tmp/run'), 'policy')

    def test_packet_overflow_precedes_persistent_mutation(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repo = Path(temp)
            task = {'ref': 'test-1', 'task': {'task_id': 'uuid', 'status': 'Open',
                    'title': 'T', 'description': 'too large', 'acceptance': None}, 'deps': []}
            cfg = deepcopy(w.config())
            cfg['worker_packet_bytes'] = 1
            args = types.SimpleNamespace(role='implement', uncertainty='local', stage=None,
                    model=None, after_model=None, escalate=False, retry_reason=None,
                    dry_run=False, task='test-1', worktree=False, prompt_file=None, timeout=10)
            with patch.object(w, 'config', return_value=cfg), \
                 patch.object(w, 'show', return_value=task), \
                 patch.object(w, 'context', return_value='saved'), \
                 patch.dict(os.environ, {'AGENT_WORKFLOW_WORKER': ''}), \
                 self.assertRaisesRegex(RuntimeError, 'limit is 1'):
                w.run_worker(args, repo)
            self.assertFalse((Path(temp) / 'state').exists())

    def test_persisted_dispatch_budget_and_retry_policy(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp)):
            selected = w.select('implement')
            first = w.reserve_dispatch(Path('/ignored'), 'task-uuid', 'implement', False,
                                       None, '000000000001', selected)
            self.assertEqual(first['attempt'], 1)
            with self.assertRaisesRegex(RuntimeError, 'retry-reason'):
                w.reserve_dispatch(Path('/another-repo'), 'task-uuid', 'implement', False,
                                   None, '000000000002', w.select('implement', override='luna'))
            second = w.reserve_dispatch(Path('/another-repo'), 'task-uuid', 'implement', True,
                                        'local approach failed', '000000000002',
                                        w.select('implement', override='luna'))
            self.assertEqual(second['attempt'], 2)
            self.assertTrue(second['escalation'])
            with self.assertRaisesRegex(RuntimeError, 'exhausted'):
                w.reserve_dispatch(Path('/ignored'), 'task-uuid', 'implement', False,
                                   'again', '000000000003', selected)
            other = w.reserve_dispatch(Path('/ignored'), 'task-uuid', 'verify', False,
                                       None, '000000000004', selected)
            self.assertEqual(other['attempt'], 1)

    def test_total_budget_across_stages_and_dry_run_is_free(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp)):
            selected = w.select('implement')
            for index in range(8):
                w.reserve_dispatch(Path('/ignored'), 'task-uuid', f'stage-{index}', False,
                                   None, f'{index:012x}', selected)
            with self.assertRaisesRegex(RuntimeError, '8 total'):
                w.reserve_dispatch(Path('/ignored'), 'task-uuid', 'stage-8', False,
                                   None, '000000000008', selected)
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp)):
            args = types.SimpleNamespace(role='implement', uncertainty='local', stage=None,
                    model='luna', after_model=None, escalate=False, dry_run=True,
                    task='test-1', worktree=False)
            with contextlib.redirect_stdout(io.StringIO()), \
                 patch.dict(os.environ, {'AGENT_WORKFLOW_WORKER': '1'}):
                w.run_worker(args, Path('/tmp'))
            self.assertFalse(Path(temp, 'dispatch-budgets.json').exists())

    def test_escalation_requires_prior_attempt_and_malformed_budget_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp)):
            with self.assertRaisesRegex(RuntimeError, 'prior attempt'):
                w.reserve_dispatch(Path('/ignored'), 'task-uuid', 'stage', True, 'cause',
                                   '000000000001', w.select('implement'))
            Path(temp, 'dispatch-budgets.json').write_text('{broken')
            with self.assertRaisesRegex(RuntimeError, 'malformed'):
                w.reserve_dispatch(Path('/ignored'), 'other-uuid', 'stage', False, None,
                                   '000000000002', w.select('implement'))

    def test_claude_telemetry_includes_helpers_and_cost(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'events.jsonl'
            path.write_text(json.dumps({
                'model': 'claude-opus-5-5', 'duration_ms': 2500,
                'usage': {'input_tokens': 10, 'output_tokens': 4},
                'total_cost_usd': 0.12,
                'modelUsage': {
                    'claude-opus-5-5': {'inputTokens': 10, 'outputTokens': 4, 'costUSD': 0.1},
                    'claude-haiku-4-5': {'inputTokens': 2, 'outputTokens': 1, 'costUSD': 0.02}}}))
            telemetry = w.parse_claude_telemetry(path)
            self.assertEqual(telemetry['observed_model'], 'claude-opus-5-5')
            self.assertEqual(telemetry['observed_models'][1]['kind'], 'helper')
            self.assertEqual(telemetry['usage']['total_tokens'], 14)
            self.assertEqual(telemetry['cost_usd'], 0.12)
            self.assertEqual(telemetry['provider_duration_seconds'], 2.5)

    def test_codex_telemetry_and_missing_failed_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'events.jsonl'
            path.write_text('\n'.join([
                json.dumps({'type': 'thread.started', 'model': 'gpt-observed'}),
                json.dumps({'type': 'turn.completed',
                            'usage': {'input_tokens': 8, 'cached_input_tokens': 3,
                                      'output_tokens': 2}})]))
            telemetry = w.parse_codex_telemetry(path)
            self.assertEqual(telemetry['observed_model'], 'gpt-observed')
            self.assertEqual(telemetry['usage']['total_tokens'], 10)
            path.write_text(json.dumps({'type': 'turn.failed', 'error': 'bad'}))
            missing = w.parse_codex_telemetry(path)
            self.assertIsNone(missing['observed_model'])
            self.assertIsNone(missing['usage'])
            self.assertIsNone(missing['cost_usd'])

    def test_claude_cache_tokens_are_separate_from_uncached_input(self):
        usage = {'input_tokens': 10, 'output_tokens': 4,
                 'cache_read_input_tokens': 100, 'cache_creation_input_tokens': 20}
        self.assertEqual(w._usage(usage, separate_cache=True)['total_tokens'], 134)
        self.assertEqual(w._usage({'input_tokens': 110, 'cached_input_tokens': 100,
                                  'output_tokens': 4})['total_tokens'], 114)

    def test_malformed_telemetry_cannot_interrupt_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'events.jsonl'
            path.write_text('[]\nnull\n')
            data = w.collect_telemetry('codex', path)
            self.assertIsNone(data['usage'])
            self.assertEqual(len(data['parse_errors']), 2)
            with patch.object(w, 'parse_claude_telemetry', side_effect=OSError('read failure')):
                self.assertIn('parse_error', w.collect_telemetry('claude', path))

    def test_verification_copy_and_scoped_report(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repo = Path(temp) / 'repo'
            repo.mkdir()
            _, folder = w.project(repo)
            run_id = '0123456789ab'
            artifacts = folder / 'runs' / run_id
            artifacts.mkdir(parents=True)
            w.write_json(artifacts / 'run.json', {
                'id': run_id, 'repo': str(repo.resolve()), 'task': 'test-1',
                'task_id': 'uuid', 'role': 'implement', 'stage': 'implement',
                'uncertainty': 'local', 'routing_rationale': 'test', 'alias': 'sol',
                'provider': 'codex', 'state': 'succeeded', 'elapsed_seconds': 1.5,
                'dispatch': {'attempt': 1, 'retry': False, 'retry_reason': None,
                             'escalation': False}, 'observed_model': None,
                'observed_models': [], 'usage': None, 'provider_cost_usd': 0})
            evidence = Path(temp) / 'evidence.txt'
            evidence.write_text('pytest: passed')
            recorded = w.verify_run(repo, run_id, 'passed', evidence)
            self.assertEqual(Path(recorded['evidence']).read_text(), 'pytest: passed')
            data = w.report(repo)
            self.assertEqual(data['rows'][0]['verification']['status'], 'passed')
            self.assertEqual(data['aggregate']['usage_unknown_runs'], 1)
            self.assertEqual(data['aggregate']['cost_usd'], 0)
            with self.assertRaises(ValueError):
                w.verify_run(repo, '../escape', 'passed', evidence)

    def exercise_worker(self, exit_code=0, timeout=False):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repo = Path(temp)
            task = {'ref': 'test-1', 'task': {'task_id': 'test-id', 'status': 'Open',
                    'title': 'Test', 'description': 'Do test', 'acceptance': None, 'notes': ''}, 'deps': []}
            calls = []
            def fake_ygg(args, cwd, **kwargs):
                calls.append(args)
                if args[:2] == ['lock', 'acquire']:
                    return types.SimpleNamespace(stdout='Lock acquired: test')
                return types.SimpleNamespace(stdout='')
            def command(selected, role, policy, output):
                self.assertIn('do not delegate', policy)
                self.assertIn('Do not commit, push, publish, merge', policy)
                if timeout:
                    code = 'import time; time.sleep(30)'
                else:
                    code = f'from pathlib import Path; Path({str(output)!r}).write_text("result"); raise SystemExit({exit_code})'
                return [os.sys.executable, '-c', code]
            args = types.SimpleNamespace(role='implement', model=None, after_model=None,
                                         escalate=False, dry_run=False, task='test-1',
                                         worktree=False, prompt_file=None, timeout=1 if timeout else 10)
            with patch.object(w, 'show', return_value=task), patch.object(w, 'context', return_value=''), \
                 patch.object(w, 'ygg', side_effect=fake_ygg), patch.object(w, 'append_notes'), \
                 patch.object(w, 'worker_command', side_effect=command), \
                 patch.object(w, 'call', return_value=types.SimpleNamespace(returncode=0, stdout=str(repo))), \
                 patch.dict(os.environ, {'AGENT_WORKFLOW_WORKER': ''}), \
                 contextlib.redirect_stdout(io.StringIO()):
                if exit_code or timeout:
                    with self.assertRaises(RuntimeError):
                        w.run_worker(args, repo)
                else:
                    w.run_worker(args, repo)
            finalizations = [c for c in calls if c[:2] == ['run', 'finalize']]
            self.assertEqual(finalizations[0][4], 'failed' if exit_code or timeout else 'succeeded')
            self.assertTrue(any(c[:2] == ['lock', 'release'] for c in calls))
            self.assertFalse(any(c[:2] == ['task', 'close'] for c in calls))
            records = list((Path(temp) / 'state').rglob('run.json'))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text())
            self.assertIn('telemetry', record)
            self.assertIn('elapsed_seconds', record)
            self.assertIsNone(record['telemetry']['provenance']['model'])
            return record

    def test_worker_success_stays_open(self):
        self.assertEqual(self.exercise_worker()['state'], 'succeeded')

    def test_process_failure_preserves_record_and_releases_lease(self):
        self.assertEqual(self.exercise_worker(exit_code=2)['state'], 'failed')

    def test_timeout_terminates_worker_and_finalizes(self):
        result = self.exercise_worker(timeout=True)
        self.assertLess(result['elapsed_seconds'], 5)
        with self.assertRaises(ProcessLookupError):
            os.kill(result['worker_pid'], 0)


class InstallerTests(unittest.TestCase):
    def test_installer_is_idempotent_preserves_config_and_handles_spaces(self):
        with tempfile.TemporaryDirectory(prefix='workflow install ') as temp:
            root = Path(temp)
            checkout = root / 'checkout with spaces' / 'workflow'
            shutil.copytree(WORKFLOW_ROOT, checkout,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            bin_dir = root / 'bin with spaces'
            skill_dir = root / 'skills with spaces'
            config_dir = root / 'config with spaces'
            config_dir.mkdir()
            models = config_dir / 'models.json'
            agents = config_dir / 'AGENTS.md'
            models.write_text('personal models\n')
            agents.write_text('personal policy\n')
            env = {**os.environ, 'AGENT_WORKFLOW_CONFIG': str(config_dir)}
            command = [str(checkout / 'install.sh'), '--with-runner', '--bin-dir', str(bin_dir),
                       '--skill-dir', str(skill_dir)]
            for _ in range(2):
                subprocess.run(command, env=env, check=True, capture_output=True, text=True)
            self.assertEqual((bin_dir / 'agent-run').resolve(),
                             (checkout / 'agent_run.py').resolve())
            self.assertEqual((skill_dir / 'agent-workflow').resolve(),
                             (checkout / 'skills/agent-workflow').resolve())
            self.assertEqual(models.read_text(), 'personal models\n')
            self.assertEqual(agents.read_text(), 'personal policy\n')

    def test_installer_refuses_regular_command_file(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp) / 'bin'
            bin_dir.mkdir()
            command_path = bin_dir / 'agent-run'
            command_path.write_text('keep me\n')
            result = subprocess.run(
                [str(WORKFLOW_ROOT / 'install.sh'), '--with-runner', '--bin-dir', str(bin_dir)],
                env=os.environ.copy(), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(command_path.read_text(), 'keep me\n')

    def test_skill_only_install_without_python_runner_or_config(self):
        with tempfile.TemporaryDirectory(prefix='skill only ') as temp:
            root = Path(temp)
            shell_tools = root / 'shell-tools'
            shell_tools.mkdir()
            for command in ('bash', 'dirname', 'mkdir', 'ln'):
                (shell_tools / command).symlink_to(shutil.which(command))
            env = {**os.environ, 'PATH': str(shell_tools),
                   'AGENT_WORKFLOW_CONFIG': str(root / 'absent-config')}
            skill_dir = root / 'skills'
            bin_dir = root / 'existing-bin'
            bin_dir.mkdir()
            runner = bin_dir / 'agent-run'
            runner.write_text('preserve existing runner')
            command = [str(WORKFLOW_ROOT / 'install.sh'), '--skill-dir', str(skill_dir),
                       '--bin-dir', str(bin_dir)]
            for _ in range(2):
                result = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(runner.read_text(), 'preserve existing runner')
            self.assertFalse((root / 'absent-config').exists())
            self.assertEqual((skill_dir / 'agent-workflow').resolve(),
                             (WORKFLOW_ROOT / 'skills/agent-workflow').resolve())
            self.assertNotIn('Setup required', result.stdout)


def tearDownModule():
    shutil.rmtree(TEST_STATE, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
