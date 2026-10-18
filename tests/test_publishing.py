from pathlib import Path
import tempfile
import unittest

from src.channels import build_channels
from src.channels.base import Post
from src.channels.threads import ThreadsChannel
from src.publishing import publish_posts, publication_state


class PublishingTests(unittest.TestCase):
    def test_factory_injection(self):
        fake = object()
        result = build_channels({'test': {'enabled': True}}, {'test': lambda settings: fake})
        self.assertIs(result['test'], fake)
        self.assertEqual(build_channels({'threads': {'enabled': False}}), {})

    def test_threads_two_step_transport(self):
        class Transport:
            def __init__(self): self.calls = []
            def json(self, url, headers, payload):
                self.calls.append((url, headers, payload))
                return {'id': '123' if len(self.calls) == 1 else '456'}
        transport = Transport()
        result = ThreadsChannel({'access_token': 'secret', 'user_id': '789'}, http=transport).publish(Post('hello'))
        self.assertEqual(result, '456')
        self.assertEqual(transport.calls[1][2], {'creation_id': '123'})
        self.assertNotIn('secret', transport.calls[0][0])

    def test_no_duplicate_after_success_or_uncertain_failure(self):
        class Fake:
            calls = 0
            fail = False
            def publish(self, post):
                self.calls += 1
                if self.fail: raise TimeoutError('secret')
                return '123'
        with tempfile.TemporaryDirectory() as folder:
            journal = Path(folder) / 'publish.sqlite3'
            channel = Fake()
            draft = {'posts': [{'text': 'first'}]}
            publish_posts(draft, {'threads': channel}, journal)
            self.assertEqual(publish_posts(draft, {'threads': channel}, journal)[0][1], 'skipped')
            channel.fail = True
            draft = {'posts': [{'text': 'second'}]}
            with self.assertRaisesRegex(ValueError, 'not confirmed'):
                publish_posts(draft, {'threads': channel}, journal)
            publish_posts(draft, {'threads': channel}, journal)
            self.assertEqual(channel.calls, 2)


if __name__ == '__main__':
    unittest.main()
