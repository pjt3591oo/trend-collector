import unittest
from unittest.mock import patch
from src.security import safe_error
from src.http_client import HTTP
from src.models import CollectionError


class SecretErrorTests(unittest.TestCase):
    def test_raw_and_escaped_secret_removed(self):
        token = 'fake-audit-secret\n'
        with patch.dict('os.environ', {'LLM_API_KEY': token}):
            message = safe_error(ValueError('Invalid header value ' + repr('Bearer '+token)))
        self.assertNotIn('fake-audit-secret', message)
        self.assertIn('[REDACTED]', message)
        self.assertNotIn('config-only-secret', safe_error('config-only-secret', {'llm':{'api_key':'config-only-secret'}}))

    def test_invalid_header_rejected_without_network_or_key(self):
        client = HTTP({'retries':0,'request_interval':0})
        with self.assertRaises(CollectionError) as error:
            client.get('https://example.invalid', {'Authorization':'Bearer fake-secret\n'})
        self.assertNotIn('fake-secret',str(error.exception))
        self.assertEqual(str(error.exception),'Invalid HTTP header configuration')
