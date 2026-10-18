import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from src.environment import load_environment, load_config


class EnvironmentTests(unittest.TestCase):
    def test_toml_references_are_resolved_after_parsing(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'TEST_KEY': 'a"\\b${OTHER}'}, clear=True):
            root = Path(folder)
            (root/'.env').write_text('TEST_MODEL=local-model\n', encoding='utf-8')
            config = root/'config.toml'
            config.write_text('[llm]\napi_key="${TEST_KEY}"\nmodels=["${TEST_MODEL}"]\n', encoding='utf-8')
            result = load_config(config)
            self.assertEqual(result['llm']['api_key'], 'a"\\b${OTHER}')
            self.assertEqual(result['llm']['models'], ['local-model'])
            config.write_text('value="${NOT_DEFINED}"', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'NOT_DEFINED'):
                load_config(config)

    def test_config_relative_loading_and_precedence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'TEST_SECRET': 'exported'}, clear=True):
            root = Path(folder)
            (root/'.env').write_text('TEST_SECRET=file\nTEST_NEW="quoted value"\nTEST_LITERAL=${TEST_SECRET}\n', encoding='utf-8-sig')
            load_environment(root/'config.toml')
            self.assertEqual(os.environ['TEST_SECRET'], 'exported')
            self.assertEqual(os.environ['TEST_NEW'], 'quoted value')
            self.assertEqual(os.environ['TEST_LITERAL'], '${TEST_SECRET}')

    def test_missing_env_is_optional(self):
        with tempfile.TemporaryDirectory() as folder:
            load_environment(Path(folder)/'config.toml')
