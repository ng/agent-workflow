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
os.environ['AGENT_WORKFLOW_PRICING'] = str(TEST_STATE / 'no-pricing.json')
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

    def test_launch_tags_session_for_dispatched_workers(self):
        with patch.object(w.os, 'execvp', side_effect=SystemExit), \
                patch.object(w, 'context', return_value=''), \
                patch.dict(os.environ, {'AGENT_WORKFLOW_SESSION': 'stale'}):
            with self.assertRaises(SystemExit):
                w.launch('claude', [])
            self.assertRegex(os.environ['AGENT_WORKFLOW_SESSION'], r'^claude-[0-9a-f]{12}$')
            self.assertEqual(w.current_session()['source'], 'agent-run launch')
        with patch.dict(os.environ, {'AGENT_WORKFLOW_SESSION': '', 'CLAUDE_CODE_SESSION_ID': 'abc'}):
            self.assertEqual(w.current_session(), {'id': 'claude-abc', 'source': 'claude'})
        with patch.dict(os.environ, {'AGENT_WORKFLOW_SESSION': '', 'CLAUDE_CODE_SESSION_ID': ''}):
            self.assertIsNone(w.current_session())

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
                 patch.dict(os.environ, {'AGENT_WORKFLOW_WORKER': '',
                                         'AGENT_WORKFLOW_SESSION': 'codex-test'}), \
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

    def exercise_worker(self, exit_code=0, timeout=False, served=None):
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
                    if served:
                        event = json.dumps({'type': 'thread.started', 'model': served})
                        code = f'print({event!r}); ' + code
                return [os.sys.executable, '-c', code]
            args = types.SimpleNamespace(role='implement', model=None, after_model=None,
                                         escalate=False, dry_run=False, task='test-1',
                                         worktree=False, prompt_file=None, timeout=1 if timeout else 10)
            with patch.object(w, 'show', return_value=task), patch.object(w, 'context', return_value=''), \
                 patch.object(w, 'ygg', side_effect=fake_ygg), patch.object(w, 'append_notes'), \
                 patch.object(w, 'worker_command', side_effect=command), \
                 patch.object(w, 'call', return_value=types.SimpleNamespace(returncode=0, stdout=str(repo))), \
                 patch.dict(os.environ, {'AGENT_WORKFLOW_WORKER': '',
                                         'AGENT_WORKFLOW_SESSION': 'codex-test'}), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()) as stderr:
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
            if not served:
                self.assertIsNone(record['telemetry']['provenance']['model'])
            run_id = record['id']
            self.assertEqual(record['session'], {'id': 'codex-test', 'source': 'agent-run launch'})
            self.assertIn(f'agent-run: implement → sol (gpt-5.6-sol) · run {run_id}',
                          stderr.getvalue())
            record['stderr'] = stderr.getvalue()
            return record

    def test_worker_success_stays_open(self):
        record = self.exercise_worker()
        self.assertEqual(record['state'], 'succeeded')
        self.assertFalse(record['model_mismatch'])
        self.assertNotIn('warning', record['stderr'])

    def test_served_model_mismatch_is_recorded_and_announced(self):
        record = self.exercise_worker(served='gpt-substitute')
        self.assertTrue(record['model_mismatch'])
        self.assertIn('warning: requested gpt-5.6-sol but gpt-substitute answered',
                      record['stderr'])
        self.assertFalse(self.exercise_worker(served='gpt-5.6-sol')['model_mismatch'])

    def test_model_matching_ignores_context_suffix_and_floating_aliases(self):
        self.assertTrue(w.model_matches('claude-opus-5-5[1m]', 'claude-opus-5-5'))
        self.assertTrue(w.model_matches('sonnet', 'claude-sonnet-5-5'))
        self.assertTrue(w.model_matches('gpt-5.6-sol', None))
        self.assertFalse(w.model_matches('claude-fable-5-1', 'claude-opus-5-5'))
        self.assertFalse(w.model_matches('sonnet', 'claude-opus-5-5'))
        self.assertEqual(w.route_line({'alias': 'opus-5.5', 'model': 'claude-opus-5-5[1m]'},
                                      'review', 'abc', escalation=True),
                         'agent-run: review → opus-5.5 (claude-opus-5-5[1m]) [escalation] · run abc')

    def test_token_parts_and_pricing(self):
        claude = w.token_parts({'input_tokens': 10, 'cached_input_tokens': 100,
                                'cache_creation_input_tokens': 20, 'output_tokens': 4}, 'claude')
        self.assertEqual(claude, {'input': 10, 'cached_input': 100, 'cache_write': 20, 'output': 4})
        codex = w.token_parts({'input_tokens': 110, 'cached_input_tokens': 100,
                               'output_tokens': 4}, 'codex')
        self.assertEqual(codex, {'input': 10, 'cached_input': 100, 'cache_write': 0, 'output': 4})
        self.assertIsNone(w.token_parts(None, 'codex'))
        self.assertIsNone(w.token_parts({'output_tokens': 1}, 'claude'))
        parts = {'input': 1_000_000, 'cached_input': 1_000_000, 'cache_write': 1_000_000,
                 'output': 1_000_000}
        self.assertAlmostEqual(w.price_cost(parts, {'input': 4, 'output': 20, 'cached_input': 0.2,
                                                    'cache_write': 8}), 32.2)
        self.assertAlmostEqual(w.price_cost(parts, {'input': 2, 'output': 10}), 16)
        cfg = w.config()
        self.assertEqual(w._price_for(cfg, 'claude-opus-4-6[1m]')['input'], 5)
        self.assertEqual(w._price_for(cfg, 'sonnet')['input'], 2)
        self.assertEqual(w._price_for(cfg, 'sonnet', 'claude-opus-5-5')['input'], 4)
        self.assertIsNone(w._price_for(cfg, 'gpt-5.6-sol'))
        self.assertIsNone(w._price_for(cfg, 'sonnet', 'claude-sonnet-4-6'))

    def test_price_and_baseline_config_are_validated(self):
        for change, message in [
                (lambda c: c['models']['sol'].update(price={'input': 1}), 'needs input and output'),
                (lambda c: c['models']['sol'].update(price={'input': 1, 'output': -1}), 'nonnegative'),
                (lambda c: c['models']['sol'].update(price={'input': 1, 'output': 1, 'x': 1}), 'not one of'),
                (lambda c: c.update(prices={'m': {'input': True, 'output': 1}}), 'nonnegative'),
                (lambda c: c['models']['sol'].update(price={'input': float('nan'), 'output': 1}), 'finite'),
                (lambda c: c.update(prices={'m': {'input': 1, 'output': float('inf')}}), 'finite'),
                (lambda c: c.update(baseline='missing'), 'baseline refers')]:
            cfg = deepcopy(w.config())
            change(cfg)
            with self.assertRaisesRegex(ValueError, message):
                w._validate_config(cfg)

    def test_stats_roll_up_by_model_route_scope_and_baseline(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repo = Path(temp) / 'repo'
            repo.mkdir()
            _, folder = w.project(repo)
            runs = [
                ('000000000001', 'review', 'opus-5.5', 'claude-opus-5-5[1m]', 'claude', 's1', 't-1',
                 'succeeded', 'claude-opus-5-5', {'input_tokens': 1_000_000, 'output_tokens': 0}, 4.0),
                ('000000000002', 'explore', 'sonnet', 'claude-sonnet-5-5[1m]', 'claude', 's1', 't-1',
                 'succeeded', 'claude-sonnet-5-5', {'input_tokens': 1_000_000, 'output_tokens': 0}, 2.0),
                ('000000000003', 'implement', 'sol', 'gpt-5.6-sol', 'codex', 's2', 't-2',
                 'failed', None, {'input_tokens': 5, 'cached_input_tokens': 2, 'output_tokens': 1}, None),
                ('000000000004', 'implement', 'sol', 'gpt-5.6-sol', 'codex', None, 't-2',
                 'succeeded', None, None, None)]
            for i, (run_id, role, alias, model, provider, session, task, state, observed,
                    usage, cost) in enumerate(runs):
                w.write_json(folder / 'runs' / run_id / 'run.json', {
                    'id': run_id, 'repo': str(repo.resolve()), 'role': role, 'alias': alias,
                    'model': model, 'provider': provider, 'task': task, 'state': state,
                    'session': {'id': session, 'source': 'test'} if session else None,
                    'created_at': f'2026-09-2{i}T00:00:00+00:00', 'elapsed_seconds': 10,
                    'dispatch': {'escalation': i == 1, 'retry': False},
                    'observed_model': observed, 'usage': usage, 'provider_cost_usd': cost})
            stats = w.run_stats()
            self.assertEqual(stats['totals']['runs'], 4)
            self.assertEqual(stats['totals']['escalations'], 1)
            self.assertEqual(stats['totals']['reported_cost_usd'], 6.0)
            route = stats['routing']['implement']['sol']
            self.assertEqual((route['runs'], route['succeeded'], route['failed'], route['escalations']),
                             (2, 1, 1, 0))
            self.assertEqual([row['full_role'] for row in w.route_rows(stats)],
                             ['explore', 'implement', 'review'])
            sol = next(b for b in stats['by_model'] if b['alias'] == 'sol')
            self.assertEqual((sol['runs'], sol['states']), (2, {'failed': 1, 'succeeded': 1}))
            self.assertEqual(sol['tokens']['input'], 3)
            self.assertEqual((sol['priced_runs'], sol['unpriced_runs'], sol['usage_runs']), (0, 1, 1))
            comparison = stats['comparison']
            self.assertEqual(comparison['baseline'], 'opus-5.5')
            self.assertEqual(comparison['runs'], 2)
            self.assertAlmostEqual(comparison['routed_usd'], 6.0)
            self.assertAlmostEqual(comparison['baseline_usd'], 8.0)
            self.assertEqual(comparison['unpriced_models'], ['gpt-5.6-sol'])
            self.assertEqual(comparison['no_usage_runs'], 1)
            self.assertEqual(w.run_stats(session='s1')['totals']['runs'], 2)
            self.assertEqual(w.run_stats(task='t-2')['totals']['runs'], 2)
            self.assertEqual(w.run_stats(since='2026-09-22T00:00:00+00:00')['totals']['runs'], 2)
            self.assertAlmostEqual(w.run_stats(baseline='sonnet')['comparison']['baseline_usd'], 4.0)
            with self.assertRaisesRegex(ValueError, 'Unknown baseline'):
                w.run_stats(baseline='missing')
            with self.assertRaisesRegex(ValueError, 'since must'):
                w.parse_since('soon')
            text = w.format_stats(stats)
            self.assertIn('All runs: $6.00 yours vs $8.00 on opus-5.5. Your mix saved $2.00 (25%) '
                          'versus using only opus-5.5.', text)
            self.assertIn('  implement → sol: 1/2 50%', text)
            self.assertIn('  explore → sonnet: 1/1 100%, $2.00/success (1 came via escalation)', text)
            self.assertIn('Not compared (no price): gpt-5.6-sol', text)
            self.assertIn('no price', text)
            self.assertIn('Your mix cost $2.00 (50% more) than using only sonnet would have.',
                          w.format_stats(w.run_stats(baseline='sonnet')))
            brief = w.brief_stats(w.run_stats(session='s1'))
            self.assertIn('session s1: 2 runs (2 ok) · 2.0M tokens · $6.00 est. at list prices · '
                          '$6.00 reported', brief)
            self.assertIn('your mix saved 25% versus using only opus-5.5', brief)
            self.assertIn('No runs in this scope.', w.format_stats(w.run_stats(session='none')))

    def write_runs(self, folder, repo, runs):
        for i, extra in enumerate(runs):
            run_id = f'{i:012x}'
            w.write_json(folder / 'runs' / run_id / 'run.json', {
                'id': run_id, 'repo': str(repo.resolve()), 'role': 'review', 'alias': 'opus-5.5',
                'model': 'claude-opus-5-5[1m]', 'provider': 'claude', 'state': 'succeeded',
                'created_at': f'2026-09-2{i}T00:00:00+00:00', **extra})

    def test_stats_review_regressions(self):
        million = {'input_tokens': 1_000_000, 'output_tokens': 0}
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repo = Path(temp) / 'repo'
            repo.mkdir()
            _, folder = w.project(repo)
            # Mixed-model Claude run: each model's usage is priced at its own rate.
            self.write_runs(folder, repo, [{
                'observed_model': 'claude-opus-5-5', 'usage': million,
                'observed_models': [
                    {'model': 'claude-opus-5-5', 'usage': million},
                    {'model': 'claude-sonnet-5-5', 'usage': million}]}])
            stats = w.run_stats()
            self.assertAlmostEqual(stats['comparison']['routed_usd'], 6.0)
            self.assertAlmostEqual(stats['comparison']['baseline_usd'], 8.0)
            self.assertEqual(stats['totals']['total_tokens'], 2_000_000)
            # A helper model without a price leaves the run unpriced instead of mispriced.
            self.write_runs(folder, repo, [{'observed_models': [
                {'model': 'claude-opus-5-5', 'usage': million},
                {'model': 'claude-haiku-4-5', 'usage': million}]}])
            self.assertEqual(w.run_stats()['comparison']['unpriced_models'], ['claude-haiku-4-5'])
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repo = Path(temp) / 'repo'
            repo.mkdir()
            _, folder = w.project(repo)
            # Order independence, active runs, missing usage, legacy provider.
            self.write_runs(folder, repo, [
                {'state': 'running', 'usage': None},
                {'usage': million, 'observed_model': 'claude-opus-5-5'},
                {'alias': 'sol', 'model': 'gpt-5.6-sol', 'provider': None,
                 'telemetry': {'provider': 'codex'},
                 'usage': {'input_tokens': 110, 'cached_input_tokens': 100, 'output_tokens': 4}}])
            stats = w.run_stats()
            opus = next(b for b in stats['by_model'] if b['alias'] == 'opus-5.5')
            self.assertEqual((opus['priced_runs'], opus['usage_runs']), (1, 1))
            sol = next(b for b in stats['by_model'] if b['alias'] == 'sol')
            self.assertEqual(sol['total_tokens'], 114)
            text = w.format_stats(stats)
            self.assertIn('4.00 (1/2)', text)
            self.assertRegex(text, r'opus-5\.5\s+claude-opus-5-5\[1m\]\s+2\s+1\s+0\s')
            self.assertIn('(1 run without usage)', w.brief_stats(stats))
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repo = Path(temp) / 'repo'
            repo.mkdir()
            _, folder = w.project(repo)
            self.write_runs(folder, repo, [{'usage': million, 'observed_model': 'claude-opus-5-5'}])
            # Baseline resolves prices the same way routed runs do.
            cfg = deepcopy(w.config())
            cfg['prices'] = {'claude-opus-5-5': {'input': 3, 'output': 15}}
            with patch.object(w, 'config', return_value=cfg):
                comparison = w.run_stats()['comparison']
            self.assertAlmostEqual(comparison['routed_usd'], comparison['baseline_usd'])
            with patch.object(w, 'config', return_value=cfg):
                self.assertIn('your mix cost the same as using only opus-5.5',
                              w.brief_stats(w.run_stats()))
            # A free baseline does not produce a percentage.
            cfg['prices'] = {'claude-sonnet-5-5': {'input': 0, 'output': 0}}
            with patch.object(w, 'config', return_value=cfg):
                stats = w.run_stats(baseline='sonnet')
            self.assertIn('Your mix cost $4.00 more than using only sonnet would have.',
                          w.format_stats(stats))
            self.assertIn('your mix cost more than using only sonnet', w.brief_stats(stats))

    def scenario_stats(self, temp):
        """Cost roles that save and one that doesn't, a weak quality route, checks, gaps."""
        repo = Path(temp) / 'repo'
        repo.mkdir()
        _, folder = w.project(repo)
        cached = {'input_tokens': 1_000_000, 'cached_input_tokens': 900_000, 'output_tokens': 0}
        runs = (
            [('implement', 'sol', 'gpt-5.6-sol', 'codex', 'succeeded', cached, None, False)] * 3
            + [('explore', 'sonnet', 'claude-sonnet-5-5[1m]', 'claude', 'succeeded',
                {'input_tokens': 1_000_000, 'output_tokens': 0}, 'passed', False),
               ('lookup', 'luna', 'gpt-5.6-luna', 'codex', 'succeeded',
                {'input_tokens': 1_000_000, 'output_tokens': 0}, None, False)]
            + [('complex', 'opus-5.5', 'claude-opus-5-5[1m]', 'claude', state,
                {'input_tokens': 100_000, 'output_tokens': 0} if index < 3 else None,
                'passed' if index == 0 else 'failed', False)
               for index, state in enumerate(['succeeded', 'succeeded', 'failed', 'failed', 'failed'])]
            + [('review', 'opus-5.5', 'claude-opus-5-5[1m]', 'claude', 'cancelled', None, None, True)])
        for index, (role, alias, model, provider, state, usage, checked, escalation) in enumerate(runs):
            run_id = f'{index:012x}'
            w.write_json(folder / 'runs' / run_id / 'run.json', {
                'id': run_id, 'repo': str(repo.resolve()), 'role': role, 'alias': alias,
                'model': model, 'provider': provider, 'state': state, 'usage': usage,
                'created_at': f'2026-09-{10 + index}T00:00:00+00:00', 'elapsed_seconds': 10,
                'dispatch': {'escalation': escalation, 'retry': False}})
            if checked:
                w.write_json(folder / 'runs' / run_id / 'verification.json', {'status': checked})
        return w.run_stats()

    def test_checks_judge_cost_roles_and_quality_routes_by_intent(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'), \
                patch.object(w, 'PRICING', WORKFLOW_ROOT / 'pricing.json'):
            stats = self.scenario_stats(temp)
        checks = w.stats_checks(stats)
        flagged = [text for flag, text in checks if flag]
        self.assertEqual(flagged[0], 'implement uses cheaper models but cost 31% more than opus-5.5 '
                         'would for the same tokens ($2.28 vs $1.74); luna would cost $0.11, '
                         'sonnet would cost $1.14')
        self.assertIn('complex → opus-5.5 passed verification 1 of 5 (20%)', flagged)
        self.assertIn('complex → opus-5.5 succeeded 2 of 5 (40%)', flagged)
        self.assertIn('3 runs recorded no usage (opus-5.5 3); totals undercount', flagged)
        self.assertFalse(any('review' in text for text in flagged))
        ok = [text for flag, text in checks if not flag][0]
        self.assertIn('cheaper models saving: lookup saved 95%, explore saved 50%', ok)
        self.assertIn('prices current', ok)
        roles = {row['role']: row for row in w.role_costs(stats)}
        self.assertTrue(roles['complex']['quality'])
        self.assertFalse(roles['implement']['quality'])
        self.assertEqual(roles['complex']['result']['short'], 'same cost')
        rows = w.route_rows(stats)
        self.assertEqual([row['full_role'] for row in rows],
                         ['lookup', 'explore', 'implement', 'complex', 'review'])
        complex_row = next(row for row in rows if row['full_role'] == 'complex')
        self.assertTrue(complex_row['weak'] and complex_row['weak_checks'])
        self.assertEqual(complex_row['verified'], '1/5')
        self.assertAlmostEqual(complex_row['per_success'], 0.6)
        review_row = next(row for row in rows if row['full_role'] == 'review')
        self.assertEqual(review_row['notes'][0][0], '1 came via escalation')
        self.assertIn('your mix saved 48% versus using only opus-5.5', w.brief_stats(stats))

    def test_panel_fits_every_width_without_cutting_words(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'), \
                patch.object(w, 'PRICING', WORKFLOW_ROOT / 'pricing.json'):
            stats = self.scenario_stats(temp)
        for width in (60, 64, 72, 80, 100, 140):
            with self.subTest(width=width):
                panel = w.format_panel(stats, width)
                lines = panel.splitlines()
                self.assertEqual({len(line) for line in lines}, {min(max(width, 60), 100)})
                self.assertTrue(lines[0].startswith('╭─ agent-run stats') and lines[-1].startswith('╰'))
                self.assertNotIn('…', panel)
                self.assertNotIn('\033[', panel)
        wide = w.format_panel(stats, 80)
        order = ['─ Checks ', '─ Routes · quality by role ', '─ Models · share of estimated cost ',
                 '─ Did cheaper models save money? · vs opus-5.5 for everything ']
        self.assertEqual(sorted(order, key=wide.index), order)
        self.assertIn('Runs      11 · 7 ok (64%) · 3 failed · 1 cancelled', wide)
        self.assertIn('Tokens    5.3M: 2.7M cache read · 2.6M in', wide)
        self.assertRegex(wide, r'│ !  complex +opus-5\.5 +2/5 +40% +1/5 +\$0\.60')
        self.assertIn('Cost roles · cheaper models by design', wide)
        self.assertLess(wide.index('Cost roles · cheaper'), wide.index('   role           yours'))
        self.assertRegex(wide, r'│ !  implement +\$2\.28 +\$1\.74  cost 31% more')
        self.assertIn('→ Your mix saved $5.26 (48%) versus using only opus-5.5.', wide)
        self.assertIn('Ignores quality: opus-5.5 might not have done every job as well.', wide)
        self.assertNotIn('█', w.format_panel(stats, 64))
        self.assertIn('\033[31m!  \033[0m', w.format_panel(stats, 80, color=True))
        empty = w.run_stats(session='nobody')
        self.assertIn('No runs in this scope.', w.format_panel(empty, 80))
        self.assertEqual(w._bar(0.5, 4), '██░░')
        self.assertEqual(w._bar(2, 4), '████')

    def test_plain_view_matches_panel_wording(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'), \
                patch.object(w, 'PRICING', WORKFLOW_ROOT / 'pricing.json'):
            stats = self.scenario_stats(temp)
        text = w.format_stats(stats)
        self.assertIn('  ! implement uses cheaper models but cost 31% more', text)
        self.assertIn('  ! complex → opus-5.5: 2/5 40%, verified 1/5, $0.60/success', text)
        self.assertIn('  ! cost role implement: $2.28 yours vs $1.74 on opus-5.5, cost 31% more', text)
        self.assertIn('    quality role complex: $1.20 yours vs $1.20 on opus-5.5, same cost', text)
        self.assertNotIn('│', text)

    def test_stats_cli_picks_plain_when_piped_and_panel_on_request(self):
        env = {**os.environ, 'AGENT_WORKFLOW_STATE': str(Path(tempfile.mkdtemp()))}
        run = lambda *extra: subprocess.run(
            [os.sys.executable, str(WORKFLOW_ROOT / 'agent_run.py'), 'stats', *extra],
            env=env, text=True, capture_output=True)
        self.assertIn('No runs in this scope.', run().stdout)
        self.assertFalse(run().stdout.startswith('╭'))
        self.assertTrue(run('--panel').stdout.startswith('╭'))
        self.assertNotEqual(run('--panel', '--plain').returncode, 0)

    def test_shipped_pricing_baseline_is_valid_dated_and_sourced(self):
        pricing = w.load_pricing(WORKFLOW_ROOT / 'pricing.json')
        dt = w.dt
        dt.date.fromisoformat(pricing['as_of'])
        self.assertEqual({source['provider'] for source in pricing['sources']}, {'anthropic', 'openai'})
        self.assertTrue(all(source['url'].startswith('https://') for source in pricing['sources']))
        for model in ('claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-1',
                      'claude-haiku-4-5', 'gpt-5.6-sol', 'gpt-6-astra', 'gpt-5.6-luna'):
            self.assertIn(model, pricing['models'])
        cfg = w.config()
        for alias, entry in cfg['models'].items():
            with self.subTest(alias=alias):
                self.assertIsNotNone(w._price_for(cfg, entry['model'], entry['model'], pricing))

    def test_pricing_precedence_staleness_and_snapshot_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'pricing.json'
            path.write_text(json.dumps({
                'as_of': '2026-09-30', 'stale_after_days': 30,
                'sources': [{'provider': 'x', 'url': 'https://example.com'}],
                'models': {'claude-opus-5-5': {'input': 1, 'output': 1},
                           'claude-haiku-4-5': {'input': 3, 'output': 3},
                           'gpt-5.6-sol': {'input': 9, 'output': 9}}}))
            pricing = w.load_pricing(path)
            cfg = w.config()
            # Config (alias price) overrides the baseline file.
            self.assertEqual(w.price_lookup(cfg, 'claude-opus-5-5[1m]', None, pricing),
                             (cfg['models']['opus-5.5']['price'], 'config'))
            self.assertEqual(w.price_lookup(cfg, 'gpt-5.6-sol', None, pricing)[1], 'pricing.json')
            self.assertEqual(w.price_lookup(cfg, 'x', 'claude-haiku-4-5-20251001', pricing)[0]['input'], 3)
            self.assertEqual(w.price_lookup(cfg, 'gpt-unknown', None, pricing), (None, None))
            status = w.pricing_status(pricing, today=w.dt.date(2026, 10, 30))
            self.assertEqual((status['age_days'], status['stale']), (30, False))
            self.assertTrue(w.pricing_status(pricing, today=w.dt.date(2026, 11, 1))['stale'])
            self.assertIsNone(w.load_pricing(Path(temp) / 'missing.json'))
            for bad in ({'models': {}}, {'as_of': 'soon', 'models': {}},
                        {'as_of': '2026-09-30', 'models': {'m': {'input': 1}}}):
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    w.load_pricing(path)
        self.assertTrue(w.model_matches('claude-haiku-4-5', 'claude-haiku-4-5-20251001'))

    def test_run_log_spans_projects_newest_first_and_flags_mismatch(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(w, 'STATE', Path(temp) / 'state'):
            repos = [Path(temp) / name for name in ('alpha', 'beta')]
            records = [
                (repos[0], '000000000001', '2026-09-30T01:00:00+00:00', 'claude-fable-5-1',
                 'claude-opus-5-5', {'total_tokens': 1200}, 0.5),
                (repos[1], '000000000002', '2026-09-30T02:00:00+00:00', 'gpt-5.6-sol',
                 None, None, None)]
            for repo, run_id, created, model, observed, usage, cost in records:
                repo.mkdir()
                _, folder = w.project(repo)
                w.write_json(folder / 'runs' / run_id / 'run.json', {
                    'id': run_id, 'repo': str(repo.resolve()), 'role': 'review',
                    'alias': 'x', 'model': model, 'state': 'succeeded',
                    'created_at': created, 'observed_model': observed,
                    'usage': usage, 'provider_cost_usd': cost})
            (Path(temp) / 'state' / 'projects' / 'junk' / 'runs' / 'bad').mkdir(parents=True)
            (Path(temp) / 'state' / 'projects' / 'junk' / 'runs' / 'bad' / 'run.json').write_text('{')
            rows = w.run_log()
            self.assertEqual([row['run_id'] for row in rows], ['000000000002', '000000000001'])
            self.assertEqual([row['model_mismatch'] for row in rows], [False, True])
            self.assertEqual([row['run_id'] for row in w.run_log(repos[0])], ['000000000001'])
            self.assertEqual(len(w.run_log(limit=1)), 1)
            text = w.format_run_log(rows)
            self.assertIn('claude-opus-5-5 !', text)
            self.assertIn('1,200', text)
            self.assertIn('$0.50', text)
            self.assertIn('served model not reported', text)
            self.assertEqual(w.format_run_log([]), 'No agent-run runs recorded.')

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
            self.assertEqual((skill_dir / 'agent-workflow-stats').resolve(),
                             (checkout / 'skills/agent-workflow-stats').resolve())
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
            for command in ('bash', 'basename', 'dirname', 'mkdir', 'ln'):
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
