"""CISA's catalog of vulnerabilities known to have been exploited."""
from collections.abc import Iterator

from src.models import CollectionError, Item
from src.security import cve_ids
from .base import BaseSource, CollectionRequest


class CISAKEVSource(BaseSource):
    name = 'cisa_kev'
    endpoint = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        data = self.http.json(self.endpoint)
        if not isinstance(data, dict) or not isinstance(data.get('vulnerabilities'), list):
            raise CollectionError('CISA KEV: expected vulnerabilities list')
        entries = data['vulnerabilities']
        if any(not isinstance(e, dict) or not e.get('dateAdded') for e in entries):
            raise CollectionError('CISA KEV: invalid catalog entry')
        entries = sorted(entries, key=lambda e: (e['dateAdded'], e.get('cveID', '')), reverse=True)
        seen = set()
        for entry in entries:
            identifiers = cve_ids(entry.get('cveID', ''))
            if len(identifiers) != 1 or not entry.get('vulnerabilityName'):
                raise CollectionError('CISA KEV: missing CVE or vulnerability name')
            cve = identifiers[0]
            if cve in seen:
                continue
            seen.add(cve)
            # dateAdded is a catalog date, not the vulnerability publication date.
            yield Item(self.name, cve, entry['vulnerabilityName'],
                       'https://www.cve.org/CVERecord?id=' + cve,
                       summary=entry.get('shortDescription', ''), tags=['security', 'kev'],
                       rank=len(seen), collection_method='official_json',
                       metrics={'known_exploited': True},
                       metadata={'cve_ids': [cve], 'date_added': entry['dateAdded'],
                                 'vendor': entry.get('vendorProject'), 'product': entry.get('product'),
                                 'required_action': entry.get('requiredAction'),
                                 'due_date': entry.get('dueDate'),
                                 'known_ransomware_campaign_use': entry.get('knownRansomwareCampaignUse'),
                                 'notes': entry.get('notes'), 'catalog_version': data.get('catalogVersion')})
            if len(seen) >= request.limit:
                break
