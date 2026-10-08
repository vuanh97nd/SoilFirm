"""Provider migration and rejection checks; no live inference or credentials."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import App
import local_ai_engine as engine
from soilfirm_agent.providers import make_provider

RETIRED = ('ollama', 'ollama_qwen', 'ollama_qwen_4b_q4',
           'ollama_qwen_4b_q8', 'ollama_qwen_coder_7b')
MODELS = ('deepseek-r1:8b', 'qwen3:8b', 'qwen3:4b-q4_K_M',
          'qwen3:4b-q8_0', 'qwen2.5-coder:7b')


class ProviderTests(unittest.TestCase):
    def test_removed_engines_rejected_before_starting_process(self):
        with patch.object(engine.mp, 'get_context') as context:
            for name in RETIRED:
                with self.subTest(engine=name), self.assertRaises(engine.LocalAIError):
                    engine.extract_geotech_local('Kiểm thử', engine=name)
                with self.assertRaises(engine.LocalAIError):
                    engine.make_local_post(engine=name)
            context.assert_not_called()

    def test_removed_agent_providers_rejected_even_with_injected_inference(self):
        infer = lambda messages: '{"answer":"unused","calls":[]}'
        for label in RETIRED + MODELS:
            with self.subTest(provider=label), self.assertRaisesRegex(ValueError, 'Unsupported provider'):
                make_provider(label, model='unused', infer=infer, environ={})

    def test_old_preferences_use_cloudflare_and_preserve_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            app = SimpleNamespace(_calculation_preferences_path=lambda: path)
            for old in MODELS + ('AI (miễn phí)', 'DeepSeek (miễn phí)', 'Qwen (miễn phí)'):
                with self.subTest(provider=old):
                    path.write_text(json.dumps({'provider': old, 'web_search': False, 'method': 'Cc/Cs/Pc'}))
                    result = App._load_calculation_preferences(app)
                    self.assertEqual(result['provider'], 'Cloudflare AI')
                    self.assertFalse(result['web_search'])
                    self.assertEqual(result['method'], 'Cc/Cs/Pc')
            for provider in ('Cloudflare AI', 'DeepSeek (g4f)', 'Gemini', 'ChatGPT'):
                path.write_text(json.dumps({'provider': provider}))
                self.assertEqual(App._load_calculation_preferences(app)['provider'], provider)
            path.write_text(json.dumps({'provider': 'DeepSeek (Miễn phí)'}))
            self.assertEqual(App._load_calculation_preferences(app)['provider'], 'DeepSeek (g4f)')

    def test_g4f_cancel_still_stops_before_inference(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            engine.extract_geotech_local('Kiểm thử', cancel=cancel, engine='g4f')

    def test_g4f_adapter_preserves_response_and_omits_credentials(self):
        with patch.object(engine, 'extract_geotech_local', return_value='{"answer":"đã đọc"}') as infer:
            response = engine.make_local_post()(None, json={
                'username': 'test-user', 'key': 'test-not-a-secret',
                'text': 'Đọc tiêu đề', 'document': {'text': 'Mã lớp'},
            })
        self.assertEqual(response.json()['source'], 'deepseek_free')
        self.assertEqual(json.loads(response.json()['answer'])['answer'], 'đã đọc')
        prompt = infer.call_args.args[0]
        self.assertIn('Mã lớp', prompt)
        self.assertNotIn('test-user', prompt)
        self.assertNotIn('test-not-a-secret', prompt)

    def test_model_errors_no_longer_offer_ollama_installation(self):
        self.assertIsNone(engine.ai_install_plan('Chưa tìm thấy Ollama', 'ollama', admin=True))
        self.assertIsNone(engine.ai_install_plan('model not found', 'qwen3:8b', admin=True))
        error = ModuleNotFoundError("No module named 'g4f'", name='g4f')
        self.assertEqual(engine.ai_install_plan(error, 'DeepSeek (g4f)', admin=True)['kind'], 'python')


if __name__ == '__main__':
    unittest.main()
