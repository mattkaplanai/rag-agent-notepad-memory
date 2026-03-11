#!/usr/bin/env python3
"""
Download PDF/PPT documents from the USDOT Air Consumer Baggage page into bilgiler/.
Source: https://www.transportation.gov/airconsumer/baggage

Run from project root: python scripts/download_baggage_docs.py
Requires: requests (install with pip install requests if needed).

Note: transportation.gov often returns 403 Forbidden for scripted requests. If that
happens, use the link list in bilgiler/USDOT_baggage_page_links.md and download
each "View PDF" / "Link" manually (e.g. open in browser → Save as → save to bilgiler).
"""

import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("This script requires 'requests'. Install with: pip install requests")
    sys.exit(1)

# Project root: parent of scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BILGILER = PROJECT_ROOT / "bilgiler"
BAGGAAGE_PAGE_URL = "https://www.transportation.gov/airconsumer/baggage"

# (filename_stem, url) – stem used for filename; extension inferred from response or URL
# Rules + Guidance + Enforcement Orders (View PDF / View PPT) from the baggage page
DOCUMENTS = [
    # Rules
    ("Response_petition_delay_14_CFR_399", "https://www.transportation.gov/airconsumer/response-petition-delay-effective-date-14-cfr-39985c-and-39987"),
    # Guidance
    ("Enforcement_policy_mishandled_baggage_wheelchairs", "https://www.transportation.gov/individuals/aviation-consumer-protection/enforcement-policy-regarding-reporting-mishandled-baggage"),
    ("Enforcement_notice_airline_reporting_mishandled_data", "https://www.transportation.gov/individuals/aviation-consumer-protection/enforcement-notice-airline-reporting-data-mishandled"),
    ("Notice_damage_wheels_handles_baggage", "https://www.transportation.gov/airconsumer/notice-baggage-guidance-112415"),
    ("DOT_presentation_baggage_provisions_EAPP_II", "https://www.transportation.gov/airconsumer/april-2011-powerpoint-presentation-summarizing-baggage-provisions"),
    ("Limits_on_baggage_settlements", "https://www.transportation.gov/airconsumer/notice-expense-reimburse-final"),
    ("Baggage_liability_international_codeshare", "https://www.transportation.gov/airconsumer/baggage-liability-international-codeshare-trips-1"),
    # Enforcement Orders
    ("EO_Allegiant_Air_2018_1_6", "https://www.transportation.gov/individuals/aviation-consumer-protection/allegiant-air-llc-order-2018-1-6"),
    ("EO_Southwest_2018_1_5", "https://www.transportation.gov/individuals/aviation-consumer-protection/southwest-airlines-co-order-2018-1-5"),
    ("EO_Frontier_2017_8_27", "https://www.transportation.gov/airconsumer/eo-2017-08-27"),
    ("EO_Hawaiian_2015_5_17", "https://www.transportation.gov/airconsumer/eo-2015-5-17"),
    ("EO_JetBlue_2014_2_9", "https://www.transportation.gov/airconsumer/eo-2014-2-9"),
    ("EO_British_Airways_2013_7_11", "https://www.transportation.gov/airconsumer/eo-2013-7-11"),
    ("EO_Korean_Air_2013_7_5", "https://www.transportation.gov/airconsumer/eo-2013-7-5"),
    ("EO_Malaysia_Airlines_2012_11_26", "https://www.transportation.gov/airconsumer/eo-2012-11-26"),
    ("EO_Jetstar_2012_10_2", "https://www.transportation.gov/airconsumer/eo-2012-10-2"),
    ("EO_Air_China_2012_9_18", "https://www.transportation.gov/airconsumer/eo-2012-9-18"),
    ("EO_Royal_Air_Maroc_2012_8_27", "https://www.transportation.gov/airconsumer/eo-2012-8-27"),
    ("EO_Santa_Barbara_Airlines_2012_8_4", "https://www.transportation.gov/airconsumer/eo-2012-8-4"),
    ("EO_Request_Extend_Compliance_2012_7_23", "https://www.transportation.gov/airconsumer/eo-2012-7-23"),
    ("EO_Alitalia_2012_1_15", "https://www.transportation.gov/airconsumer/eo-2012-1-15"),
    ("EO_Caribbean_Airlines_2011_10_20", "https://www.transportation.gov/airconsumer/eo-2011-10-20"),
    ("EO_AIRES_2011_10_2", "https://www.transportation.gov/airconsumer/eo-2011-10-2"),
    ("EO_Emirates_2011_8_24", "https://www.transportation.gov/airconsumer/eo-2011-8-24"),
    ("EO_United_2011_8_7", "https://www.transportation.gov/airconsumer/eo-2011-8-7"),
    ("EO_Lufthansa_2011_6_18", "https://www.transportation.gov/airconsumer/eo-2011-6-18"),
    ("EO_Air_France_2010_12_26", "https://www.transportation.gov/airconsumer/eo-2010-12-26"),
    ("EO_Delta_2010_10_23", "https://www.transportation.gov/airconsumer/eo-2010-10-23"),
    ("EO_EL_Al_2010_9_32", "https://www.transportation.gov/airconsumer/eo-2010-9-32"),
    ("EO_Spirit_2009_9_8", "https://www.transportation.gov/airconsumer/eo-2009-9-8"),
]


def sanitize(s: str) -> str:
    return re.sub(r"[^\w\-.]", "_", s)[:120].strip("_")


def get_extension(content_type: str, url: str) -> str:
    if content_type and "pdf" in content_type.lower():
        return ".pdf"
    if content_type and ("powerpoint" in content_type.lower() or "vnd.ms-powerpoint" in content_type.lower() or "octet-stream" in content_type.lower()):
        return ".ppt"
    if ".ppt" in url.lower() or "powerpoint" in url.lower():
        return ".ppt"
    return ".pdf"


def download_one(session: requests.Session, stem: str, url: str) -> bool:
    out_dir = BILGILER
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; USDOT-doc-downloader/1.0)",
        "Accept": "application/pdf,*/*",
    }
    try:
        r = session.get(url, headers=headers, timeout=30, allow_redirects=True)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        ext = get_extension(content_type, url)
        # If we got HTML, the site may be serving a page that links to the PDF; keep as .html for manual check
        if "text/html" in content_type:
            ext = ".html"
        path = out_dir / f"{sanitize(stem)}{ext}"
        path.write_bytes(r.content)
        print(f"  OK: {path.name}")
        return True
    except Exception as e:
        print(f"  FAIL: {url} -> {e}")
        return False


def main():
    print(f"Downloading documents from {BAGGAAGE_PAGE_URL}")
    print(f"Target folder: {BILGILER}\n")
    session = requests.Session()
    ok = 0
    for stem, url in DOCUMENTS:
        print(f"[{stem}]")
        if download_one(session, stem, url):
            ok += 1
    print(f"\nDone: {ok}/{len(DOCUMENTS)} files saved to {BILGILER}")


if __name__ == "__main__":
    main()
