#!/usr/bin/env python3
"""Second-pass country resolution: read the posting page itself.

freehire leaves some postings with no country at all (a company career site whose
location field is blank). For those the only remaining source is the posting's own
page, whose schema.org `jobPosting` block carries `jobLocation.addressCountry` -
structured data the employer published, not an inference from prose.

Results are merged into `job_scraper/country_cache.json`, marked with
`evidence: "page-jsonld"` so a later reader can tell an employer-declared country
from a URL-derived one.

Usage:
    python3 tools/resolve_country_pages.py --dry-run
    python3 tools/resolve_country_pages.py
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SEEN_PATH = "job_scraper/seen_jobs.json"
CACHE_PATH = "job_scraper/country_cache.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Name -> ISO alpha-2, for the prose fallback when a page has no JSON-LD.
NAME_CC = {
    "colombia": "co", "united states": "us", "usa": "us", "spain": "es",
    "españa": "es", "united kingdom": "gb", "australia": "au", "germany": "de",
    "india": "in", "ukraine": "ua", "poland": "pl", "netherlands": "nl",
    "czech republic": "cz", "czechia": "cz", "sweden": "se", "canada": "ca",
    "brazil": "br", "singapore": "sg", "mexico": "mx", "argentina": "ar",
    "chile": "cl", "peru": "pe", "russia": "ru", "france": "fr", "italy": "it",
    "portugal": "pt", "romania": "ro", "ireland": "ie", "israel": "il",
}


def fetch(url, timeout=25):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def countries_in_html(html):
    """Countries declared in the page: JSON-LD addressCountry first, then prose."""
    found = []
    for m in re.finditer(r'"addressCountry"\s*:\s*"([^"]+)"', html):
        code = m.group(1).strip().lower()
        if re.fullmatch(r"[a-z]{2}", code) and code not in found:
            found.append(code)
    if found:
        return found, "page-jsonld"

    # No structured location: look for a country name in the visible text.
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text).lower()
    text = re.sub(r"\s+", " ", text)
    for name in sorted(NAME_CC, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", text):
            return [NAME_CC[name]], "page-text"
    return [], "page-none"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    seen = json.load(open(SEEN_PATH, encoding="utf-8"))["seen"]
    cache = json.load(open(CACHE_PATH, encoding="utf-8"))

    # Only entries the first pass could not resolve at all.
    todo = [
        (k, v) for k, v in seen.items()
        if not (cache.get(k, {}).get("countries") or cache.get(k, {}).get("country"))
        and not str(cache.get(k, {}).get("location") or "").strip()
    ]
    print(f"{len(todo)} entries with no country and no location text", file=sys.stderr)

    def work(item):
        key, job = item
        try:
            html = fetch(job["url"])
        except urllib.error.HTTPError as e:
            return key, {"evidence": f"page-http-{e.code}"}
        except Exception as e:
            return key, {"evidence": "page-error", "note": str(e)[:120]}
        countries, ev = countries_in_html(html)
        return key, {"countries": countries, "evidence": ev}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(work, todo))

    for key, res in results:
        job = seen[key]
        print(f"  {job['company'][:30]:30s} | {res.get('countries')} | {res['evidence']}")
        if args.dry_run:
            continue
        if res.get("countries"):
            prev = cache.get(key, {})
            prev.update(res)
            prev["country"] = res["countries"][0] if len(res["countries"]) == 1 else None
            cache[key] = prev
        elif res.get("evidence"):
            prev = cache.get(key, {})
            prev["page_evidence"] = res["evidence"]
            cache[key] = prev

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nwrote {CACHE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
