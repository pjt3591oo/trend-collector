"""Shared security identifiers; URL grouping remains independent."""
import re


def cve_ids(*values: str) -> list[str]:
    return sorted({match.upper() for match in
                   re.findall(r'\bCVE-\d{4}-\d{4,}\b', ' '.join(values), re.I)})
