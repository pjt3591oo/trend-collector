import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import Mock
from src.drafts import DraftStore, generate_draft, query_drafts
from src.viewer.server import make_handler


class DraftTests(unittest.TestCase):
    def test_filters_apply_before_pagination(self):
        with tempfile.TemporaryDirectory() as folder:
            store = DraftStore(Path(folder)/'drafts.db')
            for category, source, body in [('AI','rss','alpha'),('보안','github','beta'),('AI','github','gamma')]:
                store.save({'posts':[{'text':body,'evidence':{'title':body,'category':category,'source':source}}]})
            result = query_drafts(store, Path(folder)/'missing.db', category='AI', page_size=1)
            self.assertEqual(result['total'],2)
            self.assertEqual(len(result['rows']),1)
            self.assertEqual(result['categories'],['AI','보안'])
            self.assertEqual(query_drafts(store, Path(folder)/'missing.db', category='AI', source='github', query='GAMMA')['total'],1)
            self.assertEqual(query_drafts(store, Path(folder)/'missing.db', status='published')['total'],0)

    def test_storage_and_generation_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = DraftStore(Path(folder)/'drafts.db')
            self.assertEqual(store.list()['total'], 0)
            report = {'analysis_id':'run1', 'trends':[{'evidence':[
                {'title':'title','source':'rss','url':'https://example.com'}]}]}
            generator = Mock()
            generator.generate.return_value = '본문'
            draft = generate_draft(report, [0], generator, store)
            self.assertEqual(store.list()['rows'][0], draft)
            self.assertEqual(draft['posts'][0]['evidence']['title'], 'title')
            matches = store.for_item({'source':'rss','url':'https://example.com'})
            self.assertEqual(matches[0]['draft_id'], draft['draft_id'])
            self.assertEqual(matches[0]['post_indices'], [0])
            items = [{'source':'rss','url':'https://example.com'},
                     {'source':'other','url':'https://example.com'}]
            annotated = store.annotate(items)
            self.assertTrue(annotated[0]['has_draft'])
            self.assertEqual(annotated[0]['draft_count'], 1)
            self.assertEqual(annotated[0]['latest_draft_id'], draft['draft_id'])
            self.assertFalse(annotated[1]['has_draft'])
            for selected in ([], [0,0], [1], [True], [[]]):
                with self.assertRaises(ValueError): generate_draft(report, selected, generator, store)
            self.assertEqual(store.list()['total'], 1)

    def test_http_generation_and_csrf(self):
        with tempfile.TemporaryDirectory() as folder:
            store = DraftStore(Path(folder)/'drafts.db')
            repo, generator = Mock(), Mock()
            repo.analyses.return_value = {'rows':[], 'report': {'analysis_id':'run1', 'trends':[
                {'evidence':[{'title':'news','source':'rss','url':'https://example.com'}]}]}}
            generator.generate.return_value = '생성 본문'
            channel = Mock()
            channel.publish.return_value = '12345'
            server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(repo,draft_store=store,generator_factory=lambda:generator,
                channel_factory=lambda: {'threads':channel},journal=Path(folder)/'publications.db'))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base+'/api/draft-session') as response: token=json.load(response)['token']
                body=json.dumps({'analysis_id':'run1','selected':[0]}).encode()
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base+'/api/drafts',data=body,headers={'Content-Type':'application/json'}))
                self.assertEqual(error.exception.code,403)
                generator.generate.assert_not_called()
                with urlopen(Request(base+'/api/drafts',data=body,headers={'Content-Type':'application/json','X-Draft-Token':token})) as response:
                    self.assertEqual(response.status,201)
                    draft_id = json.load(response)['draft_id']
                publish_body = json.dumps({'draft_id':draft_id,'confirmed':True}).encode()
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(Request(base+'/api/drafts/publish',data=publish_body,headers={'Content-Type':'application/json'}))
                self.assertEqual(rejected.exception.code,403)
                channel.publish.assert_not_called()
                headers={'Content-Type':'application/json','X-Draft-Token':token}
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(Request(base+'/api/drafts/publish',data=json.dumps({'draft_id':draft_id}).encode(),headers=headers))
                self.assertEqual(rejected.exception.code,400)
                channel.publish.assert_not_called()
                with urlopen(Request(base+'/api/drafts/publish',data=publish_body,headers=headers)) as response:
                    result=json.load(response)
                    self.assertTrue(result['published'])
                    self.assertEqual(result['publications'][0]['post_id'],'12345')
                with self.assertRaises(HTTPError) as duplicate:
                    urlopen(Request(base+'/api/drafts/publish',data=publish_body,headers=headers))
                self.assertEqual(duplicate.exception.code,409)
                self.assertEqual(channel.publish.call_count,1)
                with urlopen(base+'/api/draft?id='+draft_id) as response:
                    self.assertEqual(json.load(response)['publication_status'],'published')
                with urlopen(base+'/api/drafts') as response:
                    self.assertEqual(json.load(response)['total'],1)
                with urlopen(base+'/api/draft-items?id=run1') as response:
                    item = json.load(response)['items'][0]
                    self.assertTrue(item['has_draft'])
                    self.assertEqual(item['draft_count'], 1)
                    self.assertEqual(item['published_count'], 1)
                with urlopen(base+'/drafts') as response:
                    self.assertEqual(response.status,200)
            finally:
                server.shutdown();server.server_close();thread.join()
