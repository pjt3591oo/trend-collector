"""BleepingComputer official news RSS."""
from .security_rss import SecurityRSSSource


class BleepingComputerSource(SecurityRSSSource):
    name = 'bleepingcomputer'
    feed_url = 'https://www.bleepingcomputer.com/feed/'
