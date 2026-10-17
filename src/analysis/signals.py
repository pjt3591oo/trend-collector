"""Window statistics never count repeated snapshots as additional mentions."""
from datetime import datetime

METRICS = {
    'github': ('stars_total', 'forks_total'), 'hackernews': ('points', 'comments'),
    'producthunt': ('votes',), 'reddit': ('score', 'comments'),
    'huggingface': ('likes',), 'disquiet': ('votes', 'comments'),
    'indiehackers': ('votes', 'comments'),
}


def timestamp(value):
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Analysis requires timezone-aware timestamps')
    return date


def identity(row):
    return row['source'], row['external_id']


def latest(rows):
    result = {}
    for row in sorted(rows, key=lambda r: timestamp(r['observed_at'])):
        result[identity(row)] = row
    return result


def changes(rows, previous):
    histories = {}
    for row in rows:
        histories.setdefault(identity(row), []).append(row)
    result = []
    for key, values in histories.items():
        values.sort(key=lambda r: timestamp(r['observed_at']))
        first = previous.get(key, values[0])
        last = values[-1]
        if timestamp(first['observed_at']) >= timestamp(last['observed_at']):
            continue
        if first.get('collection_method') != last.get('collection_method'):
            continue
        deltas = {}
        for metric in METRICS.get(key[0], ()):
            before, after = first.get('metrics', {}).get(metric), last.get('metrics', {}).get(metric)
            if type(before) in (int, float) and type(after) in (int, float) and after != before:
                deltas[metric] = {'before': before, 'after': after, 'delta': after - before}
        before_rank, after_rank = first.get('rank'), last.get('rank')
        contexts = ('feed', 'sort', 'subreddit', 'period', 'geo', 'rank_scope')
        same_context = all(first.get('metadata', {}).get(k) == last.get('metadata', {}).get(k) for k in contexts)
        rank_change = before_rank - after_rank if same_context and type(before_rank) is int and type(after_rank) is int else None
        if deltas or rank_change:
            result.append({'source': key[0], 'external_id': key[1], 'title': last['title'],
                           'url': last['url'], 'from': first['observed_at'], 'to': last['observed_at'],
                           'metrics': deltas, 'rank_improvement': rank_change})
    return result
