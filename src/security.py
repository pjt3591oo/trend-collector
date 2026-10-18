"""Shared security identifiers; URL grouping remains independent."""
import re
import os
import json
from urllib.parse import quote, quote_plus


def safe_error(error, config=None):
    """Remove credential values and their escaped representations from display errors."""
    secrets = set()
    sensitive = re.compile(r'token|secret|password|credential|authorization|api[_-]?key', re.I)
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if sensitive.search(str(key)) and isinstance(item, str) and item:
                    secrets.add(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(dict(os.environ))
    collect(config or {})
    variants = set()
    for value in secrets:
        variants.update((value, repr(value)[1:-1], json.dumps(value, ensure_ascii=False)[1:-1], quote(value, safe=''), quote_plus(value)))
        if value.strip():
            variants.add(value.strip())
    message = str(error)
    for value in sorted(variants, key=len, reverse=True):
        message = message.replace(value, '[REDACTED]')
    # Credentials embedded in a URL can have non-secret setting names (e.g. base_url).
    message = re.sub(r'(https?://)[^/\s@]+@', r'\1[REDACTED]@', message)
    message = re.sub(r'([?&](?:access_token|token|api[_-]?key|key|secret|password|signature)=)[^&\s\'"<>]+',
                     r'\1[REDACTED]', message, flags=re.I)
    return message


def cve_ids(*values: str) -> list[str]:
    return sorted({match.upper() for match in
                   re.findall(r'\bCVE-\d{4}-\d{4,}\b', ' '.join(values), re.I)})
