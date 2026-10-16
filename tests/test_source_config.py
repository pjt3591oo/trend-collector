import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.models import Item
from trend_collector import main


class ConfigSelectionTests(unittest.TestCase):
    def test_config_selects_enabled_sources_and_excludes_unlisted_sources(self):
        class FakeSource:
            def __init__(self, name):
                self.name = name
                self.calls = 0

            def collect(self, request):
                self.calls += 1
                yield Item(self.name, '1', 'Title', 'https://example.com/1')

        sources = {name: FakeSource(name) for name in ('on', 'off', 'unlisted', 'implicit')}
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            config = Path(tmp) / 'config.toml'
            config.write_text('[sources.on]\nenabled = true\n[sources.off]\nenabled = false\n'
                              '[sources.implicit]\n', encoding='utf-8')
            code = main(['--config', str(config), '--out', tmp], sources=sources)
            manifest = json.loads(next((Path(tmp) / 'runs').glob('*/manifest.json')).read_text())
        self.assertEqual(code, 0)
        self.assertEqual(set(manifest['sources']), {'on', 'implicit'})
        self.assertEqual({name: source.calls for name, source in sources.items()},
                         {'on': 1, 'off': 0, 'unlisted': 0, 'implicit': 1})

    def test_invalid_selection_fails_before_http_or_output_creation(self):
        for content in ('[sources.geeknews]\nenabled = false\n',
                        '[sources.typo]\nenabled = true\n',
                        '[sources.geeknews]\nenabled = "false"\n'):
            with self.subTest(config=content), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / 'config.toml'
                config.write_text(content, encoding='utf-8')
                out = Path(tmp) / 'output'
                with patch('trend_collector.HTTP') as http, contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main(['--config', str(config), '--out', str(out)])
                self.assertEqual(raised.exception.code, 2)
                http.assert_not_called()
                self.assertFalse(out.exists())

    def test_removed_sources_option_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(['--sources', 'geeknews'])
        self.assertEqual(raised.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
