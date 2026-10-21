import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import search

class SearchTests(unittest.TestCase):
    def test_windows_npm_shim_resolves_to_node_without_shell(self):
        with tempfile.TemporaryDirectory(prefix='xhs windows space ') as tmp:
            shim = Path(tmp) / 'opencli.cmd'
            entry = Path(tmp) / 'node_modules/@jackwener/opencli/dist/src/main.js'
            entry.parent.mkdir(parents=True)
            entry.write_text('// synthetic installed entry')
            with patch('shutil.which', side_effect=lambda name: str(shim) if name == 'opencli' else '/verified/node.exe'):
                self.assertEqual(search.resolve_command(), ['/verified/node.exe', str(entry.resolve())])

    def test_unknown_windows_shim_is_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('shutil.which', return_value=str(Path(tmp) / 'opencli.cmd')):
                with self.assertRaises(search.SearchError):
                    search.resolve_command()

    @unittest.skipUnless(shutil.which('node'), 'Node needed only for fake-backend CLI integration test')
    def test_cli_stdin_and_explicit_js_entry(self):
        with tempfile.TemporaryDirectory(prefix='xhs cli space ') as tmp:
            fake = Path(tmp) / 'fake.mjs'
            fake.write_text('console.log(JSON.stringify([{title:process.argv[4],note_id:"abc123",xsec_token:"SYNTHETIC"}]))')
            script = Path(search.__file__)
            query = '旅行 $HOME & `echo test` "双引号"'
            completed = subprocess.run([sys.executable, str(script), '--request-stdin', '--opencli-js', str(fake)],
                input=json.dumps({'query': query}), text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            self.assertEqual(output['results'][0]['title'], query)
            self.assertIn('SYNTHETIC', output['results'][0]['share_url'])
            completed = subprocess.run([sys.executable, str(script), '--query', query, '--purpose', 'persistence', '--opencli-js', str(fake)],
                text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn('SYNTHETIC', completed.stdout)
            self.assertNotIn('share_url', completed.stdout)

    def test_filters_are_passed_as_distinct_arguments(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '[]', '')) as run:
            search.search('咖啡', command=['opencli'], sort='latest', publish_time='week')
            self.assertEqual(run.call_args.args[0][-4:], ['--sort','latest','--publish-time','week'])
            self.assertFalse(run.call_args.kwargs['shell'])

    def test_query_is_literal_argument_and_result_is_converted(self):
        with tempfile.TemporaryDirectory(prefix='xhs space ') as tmp:
            fake = Path(tmp) / 'fake cli.py'
            fake.write_text('import json,sys\nprint(json.dumps([{ "title": sys.argv[3], "url": "https://www.xiaohongshu.com/explore/abc123?xsec_token=fake"}]))\n')
            query = '咖啡 $(touch SHOULD_NOT_EXIST) `echo bad` & "报价"'
            result = search.search(query, command=[sys.executable, str(fake)])
            self.assertEqual(len(result['results']), 1)
            self.assertEqual(result['results'][0]['title'], query)
            self.assertIn('/discovery/item/abc123?source=webshare', result['results'][0]['share_url'])
            self.assertEqual(result['status'], 'ok')

    def test_backend_failure_does_not_echo_raw_output_or_claim_empty(self):
        for code in (69, 75, 77, 78, 1):
            with self.subTest(code=code):
                with patch('subprocess.run', return_value=subprocess.CompletedProcess([], code, 'PRIVATE_TOKEN', 'PRIVATE_TOKEN')):
                    with self.assertRaises(search.SearchError) as caught:
                        search.search('咖啡', command=['opencli'])
                    self.assertNotIn('PRIVATE_TOKEN', str(caught.exception))

    def test_empty_is_distinct_from_failure(self):
        for code, stdout in ((66, ''), (0, '[]')):
            with patch('subprocess.run', return_value=subprocess.CompletedProcess([], code, stdout, '')):
                output = search.search('咖啡', command=['opencli'])
                self.assertEqual(output['status'], 'empty')
                self.assertEqual(output['results'], [])

    def test_timeout_is_bounded_and_not_retried(self):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(['secret'], 12, output='PRIVATE_TOKEN')) as run:
            with self.assertRaises(search.SearchError) as caught:
                search.search('咖啡', command=['opencli'], timeout=12)
            self.assertNotIn('PRIVATE_TOKEN', str(caught.exception))
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs['timeout'], 12)

    def test_invalid_input_never_launches_backend(self):
        with patch('subprocess.run') as run:
            for query, limit in (('', 5), ('a\nb', 5), ('咖啡', 0), ('咖啡', 101), ('咖啡', True)):
                with self.assertRaises(search.SearchError):
                    search.search(query, limit=limit, command=['opencli'])
            run.assert_not_called()

    def test_bad_json_rejected_without_payload(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'PRIVATE_TOKEN', '')):
            with self.assertRaises(search.SearchError) as caught:
                search.search('咖啡', command=['opencli'])
            self.assertNotIn('PRIVATE_TOKEN', str(caught.exception))

if __name__ == '__main__':
    unittest.main()
