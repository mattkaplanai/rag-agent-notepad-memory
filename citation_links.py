"""
Citation links: map regulation/source names to official URLs for decision display.

Links point to the most specific section possible (e.g. eCFR section page instead of
whole part) so the user lands on the relevant part of the document, not the top of
a long page. Add entries to CITATION_MAP to support more docs.
"""

from pathlib import Path
from typing import Optional, Tuple

# (pattern_substring, url, optional_display_title)
# First match wins; put more specific patterns first.
# Prefer section-level URLs (e.g. section-259.4) over part-level so the user sees the relevant block, not the whole part.
CITATION_MAP = [
    # 14 CFR Sections (eCFR) — section URL = one short page, user lands on the right place
    ("14 CFR 259.4", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-259/section-259.4", "14 CFR § 259.4 (ilgili bölüm)"),
    ("14 CFR 260.5", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-260/section-260.5", "14 CFR § 260.5 (ilgili bölüm)"),
    # Parts: if text suggests delay/refund, link to §259.4 so user lands on that section
    ("14 CFR Part 259", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-259/section-259.4", "14 CFR § 259.4 (Part 259 – ilgili bölüm)"),
    ("14 CFR 259", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-259/section-259.4", "14 CFR § 259.4 (ilgili bölüm)"),
    ("14 CFR Part 260", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-260/section-260.5", "14 CFR § 260.5 (Part 260 – ilgili bölüm)"),
    ("14 CFR 260", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-260/section-260.5", "14 CFR § 260.5 (ilgili bölüm)"),
    ("14 CFR Part 254", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-254", "14 CFR Part 254 (Baggage)"),
    ("14 CFR 254", "https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-254", "14 CFR Part 254"),
    # DOT / Refunds
    ("Refunds and Other Consumer Protections", "https://www.federalregister.gov/documents/search?conditions%5Bterm%5D=Refunds+and+Other+Consumer+Protections", "DOT Final Rule: Refunds and Other Consumer Protections"),
    ("automatic refund", "https://www.transportation.gov/airconsumer/refunds", "DOT – Refunds"),
    ("significant delay", "https://www.transportation.gov/airconsumer/refunds", "DOT – Refunds (delays)"),
    ("DOT refund", "https://www.transportation.gov/airconsumer/refunds", "DOT – Refunds"),
    ("baggage fee refund", "https://www.transportation.gov/airconsumer/baggage", "DOT – Baggage"),
    ("baggage delay", "https://www.transportation.gov/airconsumer/baggage", "DOT – Baggage"),
    ("Air Consumer", "https://www.transportation.gov/airconsumer", "DOT Air Consumer"),
]


def get_citation_link(regulation_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (url, title) if regulation_text matches a known source, else (None, None).
    Uses section-level URLs where possible so the link opens the relevant part of the doc.
    """
    if not regulation_text or not isinstance(regulation_text, str):
        return None, None
    text = regulation_text.strip()
    for pattern, url, title in CITATION_MAP:
        if pattern.lower() in text.lower():
            return url, title
    return None, None


def format_regulation_with_citation(reg: str) -> str:
    """
    Format a single regulation for Markdown: if we have a link, return
    '- [title](url) — reg' or '- reg — [Resmi metin](url)'; else '- reg'.
    """
    url, title = get_citation_link(reg)
    if url and title:
        return f"- {reg} — [📎 {title}]({url})"
    return f"- {reg}"
