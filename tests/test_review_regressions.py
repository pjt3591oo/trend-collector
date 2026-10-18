"""Regression cases for the dependency review's reproduced failures."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.analysis.reporting import save_analysis
from src.channels.base import PublishError, Post
from src.channels.threads import ThreadsChannel
from src.config_display import redact
from src.drafts import DraftStore, query_drafts
from src.environment import load_application_config, load_config, resolve_settings
from src.models import CollectionError
from src.publications import PublicationRepository
from src.publishing import publish_posts, publication_state
from src.security import safe_error
from src.sources import COLLECTORS, SOURCE_TYPES


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_unused_keys_are_not_required(self):
        config = self.root/'config.toml'
        config.write_text('[collector]\noutput_dir="data"\n[sources.unused]\napi_key="${MISSING_SOURCE}"\n'
                          '[publishing.llm]\napi_key="${MISSING_LLM}"\n[channels.threads]\nenabled=false\n'
                          'access_token="${MISSING_THREADS}"\n',encoding='utf-8')
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(load_config(config,sections=('collector',)),{'collector':{'output_dir':'data'}})
            app = load_application_config(config)
            self.assertEqual(app['publishing']['llm']['api_key'],'${MISSING_LLM}')
            self.assertFalse(resolve_settings(app['channels'])['threads']['enabled'])
            with self.assertRaisesRegex(ValueError,'MISSING_LLM'):
                resolve_settings(app['publishing']['llm'])

    def test_database_failure_does_not_leave_report_files(self):
        report = {'window':{'start':'','end':''},'version':'1','classifications':[]}
        with patch('src.analysis.reporting.markdown_report',return_value='report'), patch(
                'src.analysis.reporting.sqlite3.connect',side_effect=sqlite3.OperationalError('db unavailable')):
            with self.assertRaises(sqlite3.Error):
                save_analysis(self.root/'db',report,'run',self.root/'analysis')
        self.assertFalse((self.root/'analysis'/'run').exists())

    def test_export_failure_keeps_authoritative_analysis(self):
        report = {'window':{'start':'','end':''},'version':'1','classifications':[]}
        output = self.root/'blocked'
        output.write_text('file',encoding='utf-8')
        with patch('src.analysis.reporting.markdown_report',return_value='report'):
            with self.assertRaisesRegex(OSError,'DB'):
                save_analysis(self.root/'db',report,'run',output)
        from src.analysis.repository import AnalysisRepository
        from src.viewer.repository import TrendRepository
        self.assertEqual(AnalysisRepository(self.root/'db').list()['report']['analysis_id'],'run')
        self.assertEqual(AnalysisRepository(self.root/'db').list(),TrendRepository(self.root/'db').analyses())

    def test_legacy_drafts_backfill_preserves_original_document(self):
        database = self.root/'drafts.db'
        draft = {'draft_id':'legacy','created_at':'2026','posts':[{'text':'body','evidence':{'source':'rss','url':'https://example.test','category':'AI'}}]}
        document = json.dumps(draft)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE social_drafts (draft_id TEXT PRIMARY KEY,analysis_id TEXT,created_at TEXT,draft_json TEXT)')
            db.execute('INSERT INTO social_drafts VALUES (?,?,?,?)',('legacy',None,'2026',document))
        store = DraftStore(database)
        self.assertEqual(store.get('legacy'),draft)
        self.assertEqual(store.for_item(draft['posts'][0]['evidence'])[0]['post_indices'],[0])
        DraftStore(database)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT draft_json FROM social_drafts').fetchone()[0],document)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM social_draft_posts').fetchone()[0],1)

    def test_page_decodes_only_requested_drafts_with_one_publication_snapshot(self):
        store = DraftStore(self.root/'drafts.db')
        for i in range(25):
            store.save({'posts':[{'text':f'body {i}','evidence':{'category':'AI','source':'rss'}}]})
        with patch.object(PublicationRepository,'snapshot',return_value={}) as snapshot, patch.object(
                PublicationRepository,'state',autospec=True,side_effect=lambda self,draft,snapshot: draft) as state:
            result = query_drafts(store,self.root/'journal',page_size=1)
        self.assertEqual(result['total'],25)
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(state.call_count,1)
        snapshot.assert_called_once()

    def test_definite_failure_retries_only_on_new_user_action(self):
        channel = Mock()
        channel.publish.side_effect = PublishError('rejected',uncertain=False)
        draft = {'draft_id':'one','posts':[{'text':'body'}]}
        journal = self.root/'journal'
        with self.assertRaises(ValueError): publish_posts(draft,{'threads':channel},journal)
        self.assertEqual(publication_state(draft,journal)['publication_status'],'failed')
        channel.publish.return_value = '123'
        channel.publish.side_effect = None
        publish_posts(draft,{'threads':channel},journal)
        self.assertEqual(publication_state(draft,journal)['publication_status'],'published')
        with closing(sqlite3.connect(journal)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM publication_attempts WHERE status='failed'").fetchone()[0],1)

    def test_uncertain_result_requires_confirmed_reconciliation(self):
        channel = Mock()
        channel.publish.side_effect = TimeoutError('do not expose remote payload')
        journal = self.root/'journal'
        draft = {'draft_id':'one','posts':[{'text':'body'}], 'post_indices':[7]}
        with self.assertRaises(ValueError): publish_posts(draft,{'threads':channel},journal)
        repository = PublicationRepository(journal)
        self.assertEqual(repository.state(draft)['publications'][0]['post_index'],7)
        publish_posts(draft,{'threads':channel},journal)
        self.assertEqual(channel.publish.call_count,1)
        with self.assertRaises(ValueError): repository.reconcile(draft,7,'published',post_id='123')
        with self.assertRaises(ValueError): repository.reconcile(draft,7,'published',post_id='bad',confirmed=True)
        self.assertEqual(repository.reconcile(draft,7,'published',post_id='123',confirmed=True)['publication_status'],'published')
        with self.assertRaises(ValueError): repository.reconcile(draft,7,'failed',confirmed=True)
        self.assertEqual(channel.publish.call_count,1)

    def test_threads_container_rejection_is_definite_but_publish_timeout_is_uncertain(self):
        transport = Mock()
        channel = ThreadsChannel({'access_token':'fake','user_id':'123'},http=transport)
        transport.json.side_effect = CollectionError('HTTP 401 from graph.threads.net')
        with self.assertRaises(PublishError) as error: channel.publish(Post('body'))
        self.assertFalse(error.exception.uncertain)
        transport.json.side_effect = [{'id':'1'},CollectionError('timeout')]
        with self.assertRaises(PublishError) as error: channel.publish(Post('body'))
        self.assertTrue(error.exception.uncertain)

    def test_credential_urls_are_masked_in_errors_and_config(self):
        url = 'https://user:fake-password@example.test/path?access_token=fake-token&x=ok'
        for result in [safe_error(url),redact({'base_url':url})['base_url']]:
            self.assertNotIn('fake-password',result)
            self.assertNotIn('fake-token',result)
            self.assertIn('x=ok',result)

    def test_compatibility_registry_tracks_all_official_sources(self):
        self.assertEqual(set(COLLECTORS),set(SOURCE_TYPES))

    def test_new_draft_and_evidence_index_roll_back_together(self):
        store = DraftStore(self.root/'drafts')
        with patch.object(store,'_index',side_effect=sqlite3.OperationalError('index unavailable')):
            with self.assertRaises(sqlite3.Error): store.save({'posts':[{'text':'body'}]})
        self.assertEqual(store.list()['total'],0)

    def test_concurrent_claims_allow_only_one_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        from src.publications import post_digest
        repository = PublicationRepository(self.root/'journal')
        with repository.connect(): pass
        def claim(index):
            with repository.connect() as db:
                return repository.claim(db,'threads',post_digest('body'),str(index),0)
        with ThreadPoolExecutor(max_workers=4) as workers:
            self.assertEqual(sum(workers.map(claim,range(8))),1)

    def test_reconciliation_api_requires_token_and_confirmation(self):
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from src.viewer.server import make_handler
        store = DraftStore(self.root/'drafts')
        draft = store.save({'posts':[{'text':'body'}]})
        journal = self.root/'journal'
        channel = Mock()
        channel.publish.side_effect = TimeoutError('unconfirmed')
        with self.assertRaises(ValueError): publish_posts(draft,{'threads':channel},journal)
        server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(Mock(),draft_store=store,journal=journal))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        body = {'draft_id':draft['draft_id'],'post_index':0,'status':'failed','confirmed':True}
        try:
            with urlopen(base+'/api/draft-session') as response:
                session = json.load(response)
            self.assertEqual(session['status_labels']['failed'],'발행 실패')
            headers = {'Content-Type':'application/json','X-Draft-Token':session['token']}
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+'/api/drafts/reconcile',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}))
            self.assertEqual(error.exception.code,403)
            error.exception.close()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+'/api/drafts/reconcile',data=json.dumps({**body,'confirmed':False}).encode(),headers=headers))
            self.assertEqual(error.exception.code,400)
            error.exception.close()
            self.assertEqual(publication_state(draft,journal)['publication_status'],'pending')
            with urlopen(Request(base+'/api/drafts/reconcile',data=json.dumps(body).encode(),headers=headers)) as response:
                self.assertEqual(json.load(response)['publication_status'],'failed')
            self.assertEqual(channel.publish.call_count,1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
