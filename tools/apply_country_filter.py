#!/usr/bin/env python3
"""Apply the country scope to `job_scraper/seen_jobs.json` from the resolution cache.

Reads `job_scraper/country_cache.json` (written by `tools/resolve_country.py`) and
annotates every entry with the geography it resolved to, then marks the entries
outside the accepted countries with `"status": "filtered"`.

Why a status and not a delete: `seen_jobs.json` is the dedup ledger. An entry
removed from it looks identical to a job never seen, so the next `/scrape` would
present the same out-of-scope posting again - every run, forever. Marking it
`filtered` keeps it out of the dashboard and the `/scrape` presentation while
preserving the dedup that stops it coming back. This is the same pattern the
skill already uses for `"status": "expired"` (recorded, never presented).

Usage:
    python3 tools/apply_country_filter.py --dry-run   # report, change nothing
    python3 tools/apply_country_filter.py             # write seen_jobs.json
"""

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter

SEEN_PATH = "job_scraper/seen_jobs.json"
CACHE_PATH = "job_scraper/country_cache.json"

# The accepted countries (CLAUDE.md deal-breakers, plus Australia).
ALLOWED = {"co", "us", "es", "gb", "au", "de"}
ALLOWED_NAMES = {
    "co": "Colombia", "us": "United States", "es": "Spain",
    "gb": "United Kingdom", "au": "Australia", "de": "Germany",
}

# Country names as they appear in a posting's own location string. freehire's
# `countries` facet is authoritative when present; this table is the fallback for
# postings freehire left unresolved, where the location text still states the
# country in prose ("Remote in the US", "Remote - US Only").
COUNTRY_NAMES = {
    # accepted
    "colombia": "co", "united states": "us", "usa": "us", "u.s.": "us", "u.s.a.": "us",
    # Bare "us" is safe here: location strings are short, and the word-boundary
    # lookarounds keep it from matching inside "Australia" or "Belarus".
    "us": "us",
    "spain": "es", "espana": "es", "españa": "es",
    "united kingdom": "gb", "uk": "gb", "england": "gb", "scotland": "gb", "wales": "gb",
    "australia": "au", "germany": "de", "deutschland": "de",
    # out of scope
    "india": "in", "ukraine": "ua", "russia": "ru", "brazil": "br", "brasil": "br",
    "singapore": "sg", "canada": "ca", "france": "fr", "italy": "it", "italia": "it",
    "poland": "pl", "polska": "pl", "portugal": "pt", "vietnam": "vn", "hungary": "hu",
    "peru": "pe", "japan": "jp", "latvia": "lv", "finland": "fi", "turkey": "tr",
    "south korea": "kr", "korea": "kr", "lithuania": "lt", "united arab emirates": "ae",
    "uae": "ae", "dubai": "ae", "egypt": "eg", "bangladesh": "bd", "serbia": "rs",
    "chile": "cl", "mexico": "mx", "argentina": "ar", "netherlands": "nl",
    "romania": "ro", "czechia": "cz", "czech republic": "cz", "cyprus": "cy",
    "philippines": "ph", "nigeria": "ng", "kenya": "ke", "pakistan": "pk",
    "sri lanka": "lk", "nepal": "np", "indonesia": "id", "malaysia": "my",
    "thailand": "th", "china": "cn", "taiwan": "tw", "israel": "il",
    "switzerland": "ch", "austria": "at", "sweden": "se", "norway": "no",
    "denmark": "dk", "belgium": "be", "ireland": "ie", "south africa": "za",
    "saudi arabia": "sa", "qatar": "qa", "bulgaria": "bg", "croatia": "hr",
    "estonia": "ee", "greece": "gr", "slovakia": "sk", "slovenia": "si",
    "iceland": "is", "luxembourg": "lu", "malta": "mt", "new zealand": "nz",
    "hong kong": "hk", "costa rica": "cr", "panama": "pa", "uruguay": "uy",
    "ecuador": "ec", "bolivia": "bo", "paraguay": "py", "guatemala": "gt",
    "honduras": "hn", "el salvador": "sv", "nicaragua": "ni",
    "dominican republic": "do", "venezuela": "ve", "cuba": "cu",
}

# US states, for locations that name only a state ("Remote - Georgia").
US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "hawaii", "idaho", "illinois",
    "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
    "massachusetts", "michigan", "minnesota", "mississippi", "missouri",
    "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    # "Georgia" is both a US state and a country. In a posting location it is
    # overwhelmingly the state (US employers write "Remote - Georgia"), and the
    # country would be written "Georgia, USA" or alongside a Georgian city - so
    # it resolves to the US here, the reading that matches the data.
    "georgia",
}

# Country-code TLDs that settle a posting's country on their own. Only
# unambiguous ccTLDs are listed: `.co` is skipped because it doubles as a generic
# startup domain (djinni.co is Ukrainian, not Colombian), and the ATS TLDs
# `.io`/`.ai`/`.hr`/`.cy`/`.team` are host suffixes, never geography.
TLD_CC = {
    "uk": "gb", "au": "au", "de": "de", "es": "es", "in": "in", "br": "br",
    "ca": "ca", "fr": "fr", "it": "it", "nl": "nl", "pl": "pl", "ru": "ru",
    "ua": "ua", "jp": "jp", "kr": "kr", "tr": "tr", "vn": "vn", "hu": "hu",
    "lv": "lv", "lt": "lt", "fi": "fi", "dk": "dk", "se": "se", "no": "no",
    "ie": "ie", "ch": "ch", "at": "at", "be": "be", "cz": "cz", "ro": "ro",
    "pt": "pt", "gr": "gr", "il": "il", "mx": "mx", "ar": "ar", "cl": "cl",
    "pe": "pe", "za": "za", "ae": "ae", "eg": "eg", "pk": "pk", "bd": "bd",
    "lk": "lk", "np": "np", "id": "id", "my": "my", "th": "th", "cn": "cn",
    "tw": "tw", "hk": "hk", "sg": "sg", "ph": "ph", "nz": "nz", "sa": "sa",
    "qa": "qa", "co": "co",
}
# Multi-part suffixes checked before the single-label TLD, so `.co.uk` reads as
# the UK rather than as the generic `.uk` label.
TLD_MULTI = {"co.uk": "gb", "com.au": "au", "com.co": "co", "co.nz": "nz", "com.br": "br"}

# A posting that names no country but is explicitly open worldwide is in scope:
# the profile accepts "Global Remote (hiring in these regions)".
GLOBAL_RE = re.compile(
    r"worldwide|world\s*wide|anywhere|global|work from home|international|"
    r"fully remote|100% remote|remote job|^remote$|^remoto$",
    re.I,
)
# A remote posting scoped to a macro-region that contains an accepted country.
REGION_RE = re.compile(r"latam|latin america|south america|europe|americas|emea|north america", re.I)

# Statuses that must never be overwritten by the filter: they carry a decision
# already made (ranked/expired) and `filtered` would erase it.
PRESERVE_STATUS = {"ranked", "expired"}


def countries_from_text(location):
    """Country codes named in a location string, longest name first.

    Longest-first matters: "United States" must win over a bare "States", and
    "New Zealand" over "Zealand" - matching short substrings first would let a
    partial name decide a country.
    """
    text = f" {location.lower()} "
    found = []
    for name in sorted(COUNTRY_NAMES, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", text):
            code = COUNTRY_NAMES[name]
            if code not in found:
                found.append(code)
    if not found:
        for state in sorted(US_STATES, key=len, reverse=True):
            if re.search(r"(?<![a-z])" + re.escape(state) + r"(?![a-z])", text):
                found.append("us")
                break
    return found


def country_from_host(url):
    """Country implied by a host's ccTLD, or None.

    A national TLD is the strongest cheap signal available for a posting that
    freehire left unresolved - `.zohorecruit.in` is an India-hosted board,
    `.arbeitnow.co.uk` a UK one - and it needs no network call.
    """
    host = urllib.parse.urlparse(url or "").netloc.lower().split(":")[0]
    if not host:
        return None
    for suffix, cc in TLD_MULTI.items():
        if host.endswith("." + suffix):
            return cc
    label = host.rsplit(".", 1)[-1]
    return TLD_CC.get(label)


def classify(entry, res):
    """Return (in_scope: bool, country: str|None, countries: list, reason: str).

    Evidence runs strongest-first: a country the source actually resolved, then a
    country named in the posting's own location text, then the broad remote
    signals, then the host's ccTLD, then the URL slug. Each layer only runs when
    the ones above it produced nothing, so a weak signal can never override a
    strong one - the earlier bug here was the reverse, a macro-region facet
    dropping a LATAM posting that names Colombia.
    """
    countries = [c.lower() for c in (res.get("countries") or []) if c]
    if not countries and res.get("country"):
        countries = [res["country"].lower()]
    location = str(res.get("location") or "")

    if countries:
        allowed_hit = sorted(set(countries) & ALLOWED)
        if allowed_hit:
            return True, allowed_hit[0], countries, "country-in-scope"
        return False, None, countries, "country-out-of-scope"

    # freehire had no country: read the location text before falling back.
    text_countries = countries_from_text(location)
    if text_countries:
        allowed_hit = sorted(set(text_countries) & ALLOWED)
        if allowed_hit:
            return True, allowed_hit[0], text_countries, "location-text"
        return False, None, text_countries, "location-text-out-of-scope"

    # Remote wording that names no country. "Global"/"worldwide" is in scope
    # (the profile accepts Global Remote); a macro-region is in scope only when
    # it contains an accepted country, since LATAM holds Colombia and Europe
    # holds Spain and Germany.
    if GLOBAL_RE.search(location):
        return True, None, [], "global-remote"
    if REGION_RE.search(location):
        return True, None, [], "region-remote"

    # freehire's macro-region facet, for postings whose location text was blank.
    # It distinguishes a posting open worldwide ("global") from one scoped to a
    # region the candidate is not in - the difference between keeping and
    # dropping a remote role whose country facet was never populated.
    regions = [r.lower() for r in (res.get("regions") or [])]
    if regions:
        if "global" in regions or "us" in regions or "uk" in regions:
            return True, ("us" if "us" in regions else ("gb" if "uk" in regions else None)), [], "region-facet"
        # LATAM and Europe both contain accepted countries; APAC and CIS do not.
        if set(regions) & {"latam", "eu", "europe", "north_america"}:
            return True, None, [], "region-facet-in-scope"
        return False, None, [], "region-facet-out-of-scope"

    # The host's ccTLD, when nothing above said anything.
    host_cc = country_from_host(entry.get("url"))
    if host_cc:
        if host_cc in ALLOWED:
            return True, host_cc, [host_cc], "url-tld"
        return False, None, [host_cc], "url-tld-out-of-scope"

    # A "remote"/"worldwide" marker in the URL slug is the last cheap signal
    # (e.g. `.../langchain-agents-engineer-remote-ww-2026`).
    if re.search(r"remote|worldwide|world-?wide|anywhere|-ww-?", entry.get("url", ""), re.I):
        return True, None, [], "url-slug-remote"
    return False, None, [], "unresolved"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    doc = json.load(open(SEEN_PATH, encoding="utf-8"))
    seen = doc.get("seen", {})
    cache = json.load(open(CACHE_PATH, encoding="utf-8"))

    reasons = Counter()
    kept, filtered, preserved = 0, 0, 0

    for key, entry in seen.items():
        res = cache.get(key)
        if res is None:
            # Never resolved (entry added after the cache was built). Leave it
            # untouched rather than guessing a country onto it.
            reasons["no-cache-entry"] += 1
            continue

        in_scope, country, countries, reason = classify(entry, res)
        reasons[reason] += 1

        entry["location"] = res.get("location")
        if countries:
            entry["countries"] = countries
        if country:
            entry["country"] = country
        elif in_scope:
            entry["country"] = None

        if in_scope:
            kept += 1
            continue

        if entry.get("status") in PRESERVE_STATUS:
            preserved += 1
        else:
            entry["status"] = "filtered"
            filtered += 1

    print(f"in scope        : {kept}")
    print(f"filtered        : {filtered}")
    print(f"kept as-is      : {preserved} (already ranked/expired, status preserved)")
    print("\nreasons:")
    for r, n in reasons.most_common():
        print(f"  {n:5d}  {r}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    json.dump(doc, open(SEEN_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nwrote {SEEN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
