"""KISA security notices through the officially published RSS endpoint."""
from .security_rss import SecurityRSSSource


class KISASource(SecurityRSSSource):
    name = 'kisa'
    feed_url = 'https://www.boho.or.kr/kr/rss.do?bbsId=B0000133'
