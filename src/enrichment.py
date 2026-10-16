"""Optional, injected EPSS enrichment. Failure never discards collected records."""
import math
from typing import Protocol
from urllib.parse import urlencode

from src.models import CollectionError
from src.security import cve_ids
from src.sources.base import HTTPClient


class Enricher(Protocol):
    def enrich(self, rows: list[dict]) -> dict: ...


class EPSSEnricher:
    def __init__(self, http: HTTPClient):
        self.http = http

    def enrich(self, rows: list[dict]) -> dict:
        identifiers = sorted({cve for row in rows for cve in
                              cve_ids(*row.get('metadata', {}).get('cve_ids', []))})
        scores = {}
        errors = []
        for start in range(0, len(identifiers), 100):
            batch = identifiers[start:start + 100]
            try:
                data = self.http.json('https://api.first.org/data/v1/epss?' +
                                      urlencode({'cve': ','.join(batch), 'limit': 100}))
                if not isinstance(data, dict) or data.get('status') != 'OK' or not isinstance(data.get('data'), list):
                    raise CollectionError('EPSS: invalid response')
                parsed = {}
                for entry in data['data']:
                    cve = entry['cve'].upper()
                    if cve not in batch:
                        raise CollectionError('EPSS: unexpected CVE in response')
                    score, percentile = float(entry['epss']), float(entry['percentile'])
                    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (score, percentile)):
                        raise CollectionError('EPSS: invalid probability or percentile')
                    parsed[cve] = {'probability': score, 'percentile': percentile, 'date': entry['date']}
                scores.update(parsed)
            except Exception as exc:
                errors.append(str(exc) if isinstance(exc, CollectionError) else 'EPSS: invalid response or request failed')
        for row in rows:
            matched = {cve: scores[cve] for cve in row.get('metadata', {}).get('cve_ids', []) if cve in scores}
            if matched:
                row['metrics']['epss'] = matched
        return {'status': ('partial' if scores else 'error') if errors else ('ok' if identifiers else 'empty'),
                'requested_cves': len(identifiers), 'matched_cves': len(scores),
                'missing_cves': [cve for cve in identifiers if cve not in scores],
                'errors': errors}
