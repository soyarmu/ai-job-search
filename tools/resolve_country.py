#!/usr/bin/env python3
"""Resolve each seen job's country via the freehire.me public API.

`job_scraper/seen_jobs.json` records no location, so a posting's geography can
only be recovered by looking it back up at the source it came from. freehire
stores the *source* URL verbatim (its own `url` field is the ATS link the
scraper saved), so a posting is identified by URL match, not by title guesswork:
titles repeat across employers and a title-only match would silently attach the
wrong country to a job.

Usage:
    python3 tools/resolve_country.py                # resolve, write cache
    python3 tools/resolve_country.py --report       # summarize the cache
    python3 tools/resolve_country.py --force        # ignore the cache, re-resolve

The cache (job_scraper/country_cache.json) is keyed by the seen-jobs key and is
resumable: an interrupted run keeps every lookup it already completed.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE_URL = os.environ.get("FREEHIRE_API_URL", "https://freehire.me").rstrip("/")
SEEN_PATH = "job_scraper/seen_jobs.json"
CACHE_PATH = "job_scraper/country_cache.json"

# ISO-3166 alpha-2 codes for the countries the candidate accepts (CLAUDE.md
# deal-breakers: Colombia, USA, Spain, UK, Australia, Germany). freehire's
# `countries` facet uses lowercase alpha-2; GB is the UK.
ALLOWED = {"co", "us", "es", "gb", "au", "de"}

# Country TLDs / LinkedIn country subdomains -> alpha-2. Only used as a cheap
# first pass so the API is not queried for a country the URL already states.
TLD_CC = {
    "co": "co", "uk": "gb", "es": "es", "de": "de", "us": "us", "au": "au",
    "in": "in", "sg": "sg", "br": "br", "ca": "ca", "fr": "fr", "it": "it",
    "ua": "ua", "vn": "vn", "hu": "hu", "pe": "pe", "jp": "jp", "lv": "lv",
    "fi": "fi", "tr": "tr", "kr": "kr", "lt": "lt", "ae": "ae", "eg": "eg",
    "bd": "bd", "rs": "rs", "cl": "cl", "nl": "nl", "pl": "pl", "pt": "pt",
    "mx": "mx", "ar": "ar", "ie": "ie", "ch": "ch", "at": "at", "se": "se",
    "no": "no", "dk": "dk", "be": "be", "ro": "ro", "cz": "cz",
}

# Hosts whose own domain settles the country (freehire sources them, but the
# host is a national job board rather than an employer ATS).
HOST_CC = {
    "djinni.co": "ua", "career.habr.com": "ru", "getmatch.ru": "ru",
    "nofluffjobs.com": "pl",
}


def url_key(url):
    """Identity of a posting: scheme+host+path, query/fragment stripped.

    ATS links carry tracking params (`?utm_source=freehire.me`) that differ
    between the stored copy and freehire's, while the path is stable. The same
    posting is the same path.
    """
    try:
        p = urllib.parse.urlparse(url)
    except ValueError:
        return url.lower()
    return f"{p.netloc.lower()}{p.path.rstrip('/')}".lower()


def api_get(path, retries=4):
    """GET a freehire JSON envelope. Returns None on 404, raises on hard failure."""
    url = f"{BASE_URL}{path}"
    delay = 0.5
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "resolve-country/1.0", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay = min(delay * 2, 8)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(delay)
                delay = min(delay * 2, 8)
                continue
            raise RuntimeError(f"freehire unreachable: {e}") from e
    raise RuntimeError("freehire request failed after retries")


def search(q=None, company_slug=None, limit=25):
    params = {"limit": str(limit)}
    if q:
        params["q"] = q
    if company_slug:
        params["company_slug"] = company_slug
    env = api_get(f"/api/v1/jobs/search?{urllib.parse.urlencode(params)}")
    return (env or {}).get("data", []) or []


def match_by_url(candidates, target_key):
    for j in candidates:
        if url_key(j.get("url", "")) == target_key:
            return j
    return None


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s


def resolve_one(item):
    """Resolve a single entry -> dict with country/location/source of evidence."""
    key, job = item
    url = job.get("url", "")
    host = urllib.parse.urlparse(url).netloc.lower()

    # 1. Host/domain evidence — no API call needed.
    m = re.match(r"^([a-z]{2})\.linkedin\.com$", host) or re.match(r"^([a-z]{2})\.whatjobs\.com$", host)
    if m and m.group(1) in TLD_CC:
        return key, {"country": TLD_CC[m.group(1)], "location": None, "evidence": "url-domain"}
    if host in HOST_CC:
        return key, {"country": HOST_CC[host], "location": None, "evidence": "url-domain"}

    # 2. freehire lookup, matched by URL so a title collision cannot mislabel it.
    target = url_key(url)
    title = job.get("title", "")
    company = job.get("company", "")
    attempts = [
        {"q": title, "limit": 25},
        {"company_slug": slugify(company), "limit": 100},
        {"q": f"{company} {title}".strip(), "limit": 25},
    ]
    for kwargs in attempts:
        if not kwargs.get("q") and not kwargs.get("company_slug"):
            continue
        try:
            cands = search(**kwargs)
        except Exception as e:
            return key, {"country": None, "location": None, "evidence": "error", "note": str(e)}
        hit = match_by_url(cands, target)
        if hit:
            countries = [c.lower() for c in (hit.get("countries") or [])]
            return key, {
                "country": countries[0] if len(countries) == 1 else None,
                "countries": countries,
                "location": hit.get("location"),
                "regions": hit.get("regions") or [],
                "slug": hit.get("public_slug"),
                "evidence": "freehire-url-match",
            }
    return key, {"country": None, "location": None, "evidence": "not-found"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="summarize the cache, resolve nothing")
    ap.add_argument("--force", action="store_true", help="ignore the cache and re-resolve everything")
    ap.add_argument("--workers", type=int, default=4, help="parallel API requests (default 4)")
    args = ap.parse_args()

    seen = json.load(open(SEEN_PATH, encoding="utf-8")).get("seen", {})
    cache = {}
    if os.path.exists(CACHE_PATH) and not args.force:
        cache = json.load(open(CACHE_PATH, encoding="utf-8"))

    if args.report:
        report(seen, cache)
        return 0

    todo = [(k, v) for k, v in seen.items() if k not in cache]
    print(f"{len(seen)} entries · {len(cache)} cached · {len(todo)} to resolve", file=sys.stderr)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for key, res in pool.map(resolve_one, todo):
            cache[key] = res
            done += 1
            if done % 10 == 0:
                json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
                print(f"  {done}/{len(todo)}", file=sys.stderr)

    json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"wrote {CACHE_PATH}", file=sys.stderr)
    report(seen, cache)
    return 0


def report(seen, cache):
    from collections import Counter

    ev = Counter(v.get("evidence") for v in cache.values())
    print("\n=== evidence ===")
    for k, n in ev.most_common():
        print(f"{n:5d}  {k}")

    verdicts = Counter()
    unknown = []
    for k, job in seen.items():
        r = cache.get(k)
        if not r:
            verdicts["(not resolved)"] += 1
            continue
        cs = r.get("countries") or ([r["country"]] if r.get("country") else [])
        cs = [c for c in cs if c]
        if not cs:
            verdicts["UNKNOWN"] += 1
            unknown.append((k, job.get("company"), job.get("title"), r.get("location")))
        elif set(cs) <= ALLOWED:
            verdicts["KEEP"] += 1
        elif set(cs) & ALLOWED:
            verdicts["MIXED"] += 1
        else:
            verdicts["DROP"] += 1

    print("\n=== verdicts ===")
    for k, n in verdicts.most_common():
        print(f"{n:5d}  {k}")

    if unknown:
        print(f"\n=== {len(unknown)} UNKNOWN (no country anywhere) ===")
        for u in unknown[:40]:
            print(f"  {u[1]} | {str(u[2])[:50]} | {u[3]}")


if __name__ == "__main__":
    sys.exit(main())
