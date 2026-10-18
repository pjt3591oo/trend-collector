import unittest
from src.publisher_tui import ItemFilters


class ItemFilterTests(unittest.TestCase):
    def test_combined_filters_preserve_original_indices_and_hidden_selection(self):
        state = ItemFilters([{'category': 'AI', 'source': 'github'},
                             {'category': '보안', 'source': 'rss'},
                             {'category': 'AI', 'source': 'rss'}])
        state.remember(state.visible(), [0])
        state.category = 'AI'
        state.source = 'rss'
        self.assertEqual(state.visible(), [2])
        state.remember(state.visible(), [2])
        self.assertEqual(state.selected, {0, 2})
        state.remember(state.visible(), [])
        self.assertEqual(state.selected, {0})
        state.category = '보안'
        state.source = 'github'
        self.assertEqual(state.visible(), [])
        state.remember([], [])
        self.assertEqual(state.selected, {0})
        state.category = state.source = None
        self.assertEqual(state.visible(), [0, 1, 2])
