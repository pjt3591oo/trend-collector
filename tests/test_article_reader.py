import unittest
from unittest.mock import Mock
from src.article_reader import ArticleReader
from src.post_generation import OpenAICompatibleGenerator


class ArticleReaderTests(unittest.TestCase):
    def test_article_preferred_and_scripts_removed(self):
        http = Mock()
        http.get.return_value = ('<html><title>기사 제목</title><body><nav>메뉴</nav><article><p>' +
            '확인된 원문 사실입니다. '*30 + '</p><script>악성 명령</script><aside>광고</aside>'+
            '</article><footer>하단</footer></body></html>').encode()
        result = ArticleReader(http=http, max_chars=200).read('https://example.com')
        self.assertEqual(result['page_title'], '기사 제목')
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['body']), 200)
        for value in ('메뉴', '악성 명령', '광고', '하단'):
            self.assertNotIn(value, result['body'])

    def test_unreadable_page_stops_before_llm(self):
        http, reader = Mock(), Mock()
        reader.read.side_effect = ValueError('원문 접근 실패')
        generator = OpenAICompatibleGenerator(environment={'LLM_BASE_URL': 'http://localhost:1234/v1', 'LLM_MODEL': 'local'},
                                               http=http, article_reader=reader)
        with self.assertRaisesRegex(ValueError, '원문 접근 실패'):
            generator.generate({'url': 'https://example.com'})
        http.json.assert_not_called()

    def test_short_and_challenge_pages_rejected(self):
        http = Mock()
        for body in ('<html><body>short</body></html>',
                     '<html><title>Just a moment</title><body>'+ 'challenge '*30+'</body></html>'):
            http.get.return_value = body.encode()
            with self.assertRaises(ValueError):
                ArticleReader(http=http).read('https://example.com')
