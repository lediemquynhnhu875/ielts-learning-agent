import io, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import app
import settings

class OpenRouterTests(unittest.TestCase):
    def test_null_message_is_recoverable(self):
        with self.assertRaises(app.ModelOutputError):
            app.parse_model_response({'choices':[{'message':None}]})
    def test_wrong_choices_is_recoverable(self):
        with self.assertRaises(app.ModelOutputError):
            app.parse_model_response({'choices':{'bad':'shape'}})
    def test_truncated_json_content(self):
        with self.assertRaises(app.ModelOutputError):
            app.parse_model_response({'choices':[{'message':{'content':'{"criteria":[{"comment":"unfinished'}}]})
    def test_length_finish_reason(self):
        with self.assertRaisesRegex(app.ModelOutputError,'token'):
            app.parse_model_response({'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})
    def test_malformed_output_regenerated(self):
        data={'mode':'live','prompt_text':'Question','essay_text':'A unique sentence.'}
        rubric=app.get_writing_rubric('demo')
        valid=app.demo_judge('A',data,rubric)
        with patch.object(app,'call_model',side_effect=[app.ModelOutputError('Incomplete JSON'),valid]) as call:
            output, trace=app.run_judge('A',data,rubric)
        self.assertEqual(call.call_count,2)
        self.assertEqual(trace[0]['step'],'parse_A')
        self.assertEqual(trace[-1]['errors'],[])
    def test_shared_key_and_feedback_role(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'fixture-only','WRITING_A_MODEL':'test/model'}, clear=True):
            self.assertEqual(settings.model_config('FEEDBACK'), ('https://openrouter.ai/api/v1','test/model','fixture-only'))
    def test_local_env_does_not_override_shell(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WRITING_A_MODEL':'shell/model'}, clear=True):
            path = Path(tmp) / '.env'
            path.write_text('OPENROUTER_API_KEY="fixture"\nWRITING_A_MODEL=file/model\n',encoding='utf-8')
            settings.load_env(path)
            self.assertEqual(os.environ['OPENROUTER_API_KEY'], 'fixture')
            self.assertEqual(os.environ['WRITING_A_MODEL'], 'shell/model')
    def test_request_endpoint_and_json(self):
        response = io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"criteria":[]}'}}]}).encode())
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'fixture','WRITING_A_MODEL':'test/model'}, clear=True), patch.object(app, 'urlopen', return_value=response) as call:
            self.assertEqual(app.call_model('A', {'essay_text':'example'}), {'criteria':[]})
            req = call.call_args.args[0]
            self.assertEqual(req.full_url, 'https://openrouter.ai/api/v1/chat/completions')
            self.assertEqual(json.loads(req.data)['provider'], {'require_parameters':True})
    def test_auth_error_redacted(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'fixture','WRITING_A_MODEL':'test/model'}, clear=True), patch.object(app, 'urlopen', side_effect=HTTPError('https://example',401,'secret-provider-body',{},None)):
            with self.assertRaisesRegex(ValueError, '401') as caught: app.call_model('A', {})
            self.assertNotIn('secret-provider-body', str(caught.exception))
    def test_502_retry_then_success(self):
        response = io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"ok":true}'}}]}).encode())
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'fixture','WRITING_A_MODEL':'test/model'}, clear=True), patch.object(app.time,'sleep'), patch.object(app,'urlopen',side_effect=[HTTPError('https://example',502,'bad gateway',{},None),response]) as call:
            self.assertEqual(app.call_model('A',{}), {'ok':True})
            self.assertEqual(call.call_count,2)
    def test_502_bounded(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'fixture','WRITING_A_MODEL':'test/model'}, clear=True), patch.object(app.time,'sleep'), patch.object(app,'urlopen',side_effect=HTTPError('https://example',502,'bad gateway',{},None)) as call:
            with self.assertRaisesRegex(ValueError,'502'): app.call_model('A',{})
            self.assertEqual(call.call_count,3)

if __name__ == '__main__': unittest.main(verbosity=2)
