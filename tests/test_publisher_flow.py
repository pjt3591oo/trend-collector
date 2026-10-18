import json
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from src.post_generation import OpenAICompatibleGenerator
from trend_publisher import main
from src.drafts import DraftStore


class PublisherFlowTests(unittest.TestCase):
    def test_local_completion_and_validation(self):
        http = Mock()
        http.json.return_value = {'choices': [{'message': {'content': '새로운 도구 소식입니다.'}}]}
        reader = Mock()
        reader.read.return_value = {'page_title': '원문', 'body': '실제 원문 내용', 'truncated': False}
        generator = OpenAICompatibleGenerator(environment={'LLM_BASE_URL': 'http://127.0.0.1:1234/v1',
                                               'LLM_MODEL': 'local'}, http=http, article_reader=reader)
        item = {'title': '도구 출시', 'category': '개발', 'source': 'news', 'url': 'https://example.com'}
        self.assertTrue(generator.generate(item).endswith(item['url']))
        reader.read.assert_called_once_with(item['url'])
        context = json.loads(http.json.call_args.args[2]['messages'][1]['content'])
        self.assertEqual(context['body'], '실제 원문 내용')
        self.assertEqual(http.json.call_args.args[0], 'http://127.0.0.1:1234/v1/chat/completions')
        http.json.return_value = {'choices': [{'message': {'content': 'a'*501}}]}
        with self.assertRaises(ValueError): generator.generate(item)

    def test_selection_generation_preview_confirmation(self):
        for answer in ('n', 'y'):
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                folder = root/'analysis'/'run1'
                folder.mkdir(parents=True)
                report = {'analysis_id': 'run1', 'trends': [{'primary_category': 'AI', 'evidence': [
                    {'title': 'first', 'url': 'https://a.example', 'source': 'a'},
                    {'title': 'second', 'url': 'https://b.example', 'source': 'b'}]}]}
                with closing(sqlite3.connect(root/'analyses.sqlite3')) as db, db:
                    db.execute('CREATE TABLE analysis_runs (analysis_id TEXT,created_at TEXT,window_start TEXT,window_end TEXT,version TEXT,report_json TEXT)')
                    db.execute('INSERT INTO analysis_runs VALUES (?,?,?,?,?,?)',('run1','2026','','','1',json.dumps(report)))
                config = root/'config.toml'
                config.write_text('[publishing]\nanalysis_dir = '+json.dumps(str(root/'analysis'))+
                    '\nanalysis_database = '+json.dumps(str(root/'analyses.sqlite3'))+
                    '\ndraft_database = '+json.dumps(str(root/'drafts.sqlite3'))+
                    '\njournal = '+json.dumps(str(root/'journal.sqlite3'))+'\n', encoding='utf-8')
                generator = Mock()
                generator.generate.return_value = 'generated text'
                channel = Mock()
                channel.publish.return_value = '123'
                factory = Mock(return_value={'threads': channel})
                ui = Mock()
                ui.select_report.return_value = 'run1'
                ui.select_items.return_value = [1]
                ui.choose_draft.return_value = 'new'
                ui.preview.return_value = True
                ui.confirm.return_value = answer == 'y'
                ui.work.side_effect = lambda title, callback: callback(lambda _: None)
                self.assertEqual(main(['--config', str(config)], ui=ui, generator_factory=lambda settings: generator, channel_factory=factory), 0)
                self.assertEqual(generator.generate.call_args.args[0]['title'], 'second')
                ui.preview.assert_called_once()
                ui.confirm.assert_called_once()
                self.assertEqual(channel.publish.call_count, int(answer == 'y'))
                self.assertEqual(factory.call_count, int(answer == 'y'))
                self.assertEqual(len(list(folder.glob('social-draft-*.json'))), 0)
                self.assertEqual(DraftStore(root/'drafts.sqlite3').list()['total'], 1)
                # Reopen an existing draft without invoking generation or creating a copy.
                ui.choose_draft.return_value = 0
                ui.preview.return_value = False
                unused_generator = Mock()
                main(['--config', str(config)], ui=ui, generator_factory=unused_generator, channel_factory=factory)
                unused_generator.assert_not_called()
                candidates = ui.choose_draft.call_args.args[1]
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0]['publication_status'], 'published' if answer == 'y' else 'draft')
                self.assertEqual(DraftStore(root/'drafts.sqlite3').list()['total'], 1)

    def test_cancel_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            config = path/'config.toml'
            config.write_text('[publishing]\nanalysis_dir = '+json.dumps(str(path/'analysis'))+'\n', encoding='utf-8')
            folder = path/'analysis'/'run1'
            folder.mkdir(parents=True)
            report = folder/'report.json'
            report.write_text(json.dumps({'trends': [{'evidence': [
                {'title': 'title', 'url': 'https://example.com', 'source': 'test'}]}]}), encoding='utf-8')
            factory = Mock()
            ui = Mock()
            ui.select_report.return_value = None
            main(['--config', str(config)], ui=ui, generator_factory=factory)
            factory.assert_not_called()
