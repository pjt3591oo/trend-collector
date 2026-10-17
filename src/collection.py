"""Collect one source independently, preserving items on partial failures."""
from .models import CollectionError, Skipped
from .sources import CollectionRequest, Source


def collect_source(source: Source, request: CollectionRequest):
    records = {}
    status, message = 'ok', ''
    try:
        for item in source.collect(request):
            record = item.record()
            records[record['external_id']] = record
    except Skipped as exc:
        status, message = 'skipped', str(exc)
    except Exception as exc:
        status = 'partial' if records else 'error'
        message = str(exc) if isinstance(exc, CollectionError) else f'{type(exc).__name__}: invalid response or configuration'
    if status == 'ok' and not records:
        status, message = 'empty', 'No items returned; check window, filters, or source availability'
    result = {'status': status, 'count': len(records), 'message': message}
    if hasattr(source, 'filter_counts'):
        result['filter'] = dict(source.filter_counts)
        if status == 'empty' and source.filter_counts.get('filtered'):
            result['message'] = 'No items matched the configured category/keywords'
    return list(records.values()), result
