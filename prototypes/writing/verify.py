"""Generate a functional eval report and test actual local HTTP requests."""
import io, json, threading, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import app
import test_app
import test_openrouter

def main():
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_app.WritingEval)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_openrouter.OpenRouterTests))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    http_checks = []
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        (temp / 'index.html').write_bytes((app.ROOT / 'index.html').read_bytes())
        with patch.object(app, 'ROOT', temp):
            server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base) as response:
                    assert 'Writing Lab' in response.read().decode(); http_checks.append('GET UI: PASS')
                payload = {'mode': 'demo', 'prompt_text': 'Should students learn practical skills?', 'essay_text': 'Many students benefit from practical skills. Theory remains important.'}
                request = Request(base + '/api/assess', json.dumps(payload).encode(), {'Content-Type': 'application/json'})
                with urlopen(request) as response: demo = json.load(response)
                assert demo['status'] == 'demo' and demo['overall_band'] is None and demo['reconciliation']['disputed'] == ['TR']
                http_checks.append('POST demo, validators, moderator, persistence: PASS')
                invalid = Request(base + '/api/assess', b'{}', {'Content-Type': 'application/json'})
                try: urlopen(invalid); raise AssertionError('Empty input accepted')
                except HTTPError as exc: assert exc.code == 400
                http_checks.append('POST invalid input: PASS')
                foreign = Request(base + '/api/assess', json.dumps(payload).encode(), {'Content-Type': 'application/json', 'Origin': 'https://untrusted.example'})
                try: urlopen(foreign); raise AssertionError('Foreign origin accepted')
                except HTTPError as exc: assert exc.code == 403
                http_checks.append('Foreign browser origin rejected: PASS')
            finally:
                server.shutdown(); server.server_close(); thread.join()
    root = Path(__file__).resolve().parent
    report = '# Functional evaluation report\n\n' + f'Passed: {result.testsRun - len(result.errors) - len(result.failures)}/{result.testsRun}\n\n' + '\n'.join(http_checks) + '\n\n```text\n' + stream.getvalue() + '```\n\nNo live provider calls or band accuracy benchmark were performed.\n'
    (root / 'EVAL_REPORT.md').write_text(report, encoding='utf-8')
    (root / 'DEMO_RESULT.json').write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding='utf-8')
    print(report)
    if not result.wasSuccessful(): raise SystemExit(1)

if __name__ == '__main__': main()
