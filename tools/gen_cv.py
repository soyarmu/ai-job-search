#!/usr/bin/env python3
"""Lean CV generator. One LLM call picks IDs from cv/master.json, one LaTeX compile,
then records the tracker row and archives the posting (replaces /apply Step 6b).

Usage:
  python3 tools/gen_cv.py "https://company.com/job/123"
  python3 tools/gen_cv.py --file job.txt [--source URL]
  python3 tools/gen_cv.py --dry-run --company X --role Y   (no LLM call)
Env: GEMINI_API_KEY (or GOOGLE_API_KEY); optional CV_MODEL (default gemini-2.5-flash-lite)
"""
import argparse, csv, datetime, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CV_DIR = os.path.join(ROOT, "cv")
MASTER = os.path.join(CV_DIR, "master.json")
TRACKER = os.path.join(ROOT, "job_search_tracker.csv")
HEADER = ["date", "company", "sector", "role", "role_type", "channel", "status", "contact_person",
          "fit_rating", "notes", "cv_file", "cover_letter_file", "source", "deadline"]
# ASSUMPTION: align with "Tracker status vocabulary" in .claude/commands/outcome.md
FINAL = {"hired", "rejected", "no_response", "offer_declined", "withdrawn", "no response", "offer declined"}
MODEL = os.environ.get("CV_MODEL", "gemini-2.5-flash-lite")
MAX_POSTING = 8000


def die(msg):
    sys.exit("ERROR: " + msg)


def clean_field(s):
    """Tracker fields: no commas, quotes or line breaks."""
    return re.sub(r'[,"\r\n]+', " -" if "," in str(s) else " ", str(s)).strip()


def slug(company, role):
    return re.sub(r"[^A-Za-z0-9]+", "_", f"{company} {role}").strip("_")[:80]


# ---------- input ----------
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:
        die(f"could not fetch URL ({e}). Paste the posting text with --file instead.")
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def get_posting(args):
    if args.file:
        return open(args.file, encoding="utf-8").read(), args.source or ""
    if args.posting and re.match(r"https?://", args.posting.strip()):
        return fetch(args.posting.strip()), args.posting.strip()
    if args.posting:
        return args.posting, args.source or ""
    if not sys.stdin.isatty():
        return sys.stdin.read(), args.source or ""
    return "", ""


# ---------- LLM ----------
def catalog(m):
    lines = ["SUMMARIES:"] + [f"- {s['id']}: {s['text'][:100]}" for s in m["summaries"]]
    lines.append("SKILLS (use exact names):")
    lines += [f"- {g}: " + "; ".join(v) for g, v in m["skills"].items()]
    lines.append("BULLETS (id [tags] text):")
    for j in m["jobs"]:
        for b in j["bullets"]:
            lines.append(f"- {b['id']} [{','.join(b['tags'])}] ({j['company']}) {b['text'][:110]}")
    return "\n".join(lines)


SYSTEM = ("You select content for a tailored CV. Use ONLY ids and skill names that appear in the CATALOG. "
          "Never invent, reword or add experience. Be honest: fit_rating is a bare integer 0-100; "
          "gaps = requirements in the posting the catalog does not support (max 5, short phrases). "
          "deadline = YYYY-MM-DD only if the posting explicitly states one, else empty string. "
          "company and role exactly as the posting names them. "
          "summary is a neutral one-line description of the role (max 40 words): what it does, main stack, "
          "seniority, location/remote. No hype.")

SUMMARY_SYSTEM = ("You summarize a job posting neutrally. No hype. "
                  "company and role exactly as the posting names them. "
                  "summary is max 40 words: what the role does, main stack, seniority, location/remote.")

SCHEMA = {"type": "OBJECT", "properties": {
    "company": {"type": "STRING"}, "role": {"type": "STRING"}, "deadline": {"type": "STRING"},
    "fit_rating": {"type": "INTEGER"}, "summary_id": {"type": "STRING"},
    "summary": {"type": "STRING"},
    "skill_names": {"type": "ARRAY", "items": {"type": "STRING"}},
    "bullet_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
    "gaps": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["company", "role", "deadline", "fit_rating", "summary_id", "summary", "skill_names", "bullet_ids", "gaps"]}

SUMMARY_SCHEMA = {"type": "OBJECT", "properties": {
    "company": {"type": "STRING"}, "role": {"type": "STRING"}, "summary": {"type": "STRING"}},
    "required": ["company", "role", "summary"]}


def call_llm_raw(system, user, schema):
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        die("set GEMINI_API_KEY")
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                                 "temperature": 0.2}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(4 * (attempt + 1))
                continue
            die(f"LLM HTTP {e.code}: {e.read().decode()[:300]}")
    try:
        sel = json.loads(resp["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        die("unexpected LLM response: " + json.dumps(resp)[:300])
    sel["_tokens"] = resp.get("usageMetadata", {}).get("totalTokenCount", "?")
    return sel


def call_llm(posting, m):
    user = (f"POSTING:\n{posting[:MAX_POSTING]}\n\nCATALOG:\n{catalog(m)}\n\n"
            "Pick: summary_id (1), summary (max 40 words), skill_names (max 24, most relevant first), "
            "bullet_ids (max 12, most relevant first).")
    return call_llm_raw(SYSTEM, user, SCHEMA)


def summarize_llm(posting):
    user = f"POSTING:\n{posting[:MAX_POSTING]}\n\nGive company, role, and a neutral max-40-word summary."
    return call_llm_raw(SUMMARY_SYSTEM, user, SUMMARY_SCHEMA)


def dry_selection(m, args):
    return {"company": args.company or "", "role": args.role or "", "deadline": "", "fit_rating": 0,
            "summary_id": m["summaries"][0]["id"],
            "skill_names": [s for v in m["skills"].values() for s in v],
            "bullet_ids": [b["id"] for j in m["jobs"] for b in j["bullets"]], "gaps": [], "_tokens": 0}


# ---------- LaTeX ----------
def esc(s):
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
           "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(c, c) for c in s)


PREAMBLE = r"""\documentclass[11pt,a4paper,sans]{moderncv}
\moderncvstyle{banking}
\moderncvcolor{blue}
\renewcommand*{\namefont}{\fontsize{34}{36}\bfseries\upshape}
\colorlet{firstnamecolor}{color1}
\colorlet{lastnamecolor}{color1}
\colorlet{namecolor}{color1}
\renewcommand*{\sectionstyle}[1]{{\sectionfont\color{color1}#1}}
\usepackage[utf8]{inputenc}
\ifpdftex\usepackage[T1]{fontenc}\fi
\AtEndPreamble{\hypersetup{colorlinks=true,linkcolor=blue,filecolor=magenta,urlcolor=blue,pdftitle={@TITLE@},pdfpagemode=UseNone,}}
\usepackage[scale=0.77]{geometry}
\usepackage{import}
"""


def pick_content(m, sel):
    sums = {s["id"]: s["text"] for s in m["summaries"]}
    summary = sums.get(sel["summary_id"]) or m["summaries"][0]["text"]
    wanted = set(sel["skill_names"])
    skills = {g: [s for s in v if s in wanted] for g, v in m["skills"].items()}
    skills = {g: v for g, v in skills.items() if v}
    order = {b: i for i, b in enumerate(sel["bullet_ids"])}
    jobs = []
    for j in m["jobs"]:
        chosen = sorted([b for b in j["bullets"] if b["id"] in order], key=lambda b: order[b["id"]])
        chosen = chosen[: j["max_bullets"]]
        if len(chosen) < j.get("min_bullets", 1):
            for b in j["bullets"]:
                if b not in chosen and len(chosen) < j.get("min_bullets", 1):
                    chosen.append(b)
        jobs.append((j, chosen))
    return summary, skills, jobs


def build_tex(m, sel):
    p = m["personal"]
    summary, skills, jobs = pick_content(m, sel)
    t = PREAMBLE.replace("@TITLE@", esc(f"{p['first']} {p['last']} - CV"))
    t += (f"\\name{{{esc(p['first'])}}}{{{esc(p['last'])}}}\n\\address{{{esc(p['address'])}}}{{}}{{}}\n"
          f"\\phone[mobile]{{{esc(p['phone'])}}}\n\\email{{{esc(p['email'])}}}\n"
          f"\\extrainfo{{\\href{{{p['linkedin']}}}{{LinkedIn}}, \\href{{{p['github']}}}{{GitHub}}}}\n")
    t += "\\begin{document}\n\\makecvtitle\n\n\\section{Profile}\n\\cvitem{}{" + esc(summary) + "}\n\n\\section{Skills}\n"
    for g, v in skills.items():
        t += f"\\cvitem{{{esc(g)}}}{{{esc(', '.join(v))}}}\n"
    t += "\n\\section{Professional Experience}\n"
    for j, bl in jobs:
        items = "\n".join(f"\\item {esc(b['text'])}" for b in bl)
        t += (f"\\cventry{{{esc(j['dates'])}}}{{{esc(j['title'])}}}{{{esc(j['company'])}}}{{{esc(j['location'])}}}"
              f"{{{esc(j['project'])}}}{{\\begin{{itemize}}\n{items}\n\\end{{itemize}}}}\n")
    t += "\n\\section{Education}\n"
    for e in m["education"]:
        t += f"\\cventry{{{esc(e['dates'])}}}{{{esc(e['title'])}}}{{{esc(e['school'])}}}{{{esc(e['location'])}}}{{}}{{}}\n"
    t += "\n\\section{Certifications}\n\\cvitem{}{" + esc(" · ".join(m["certifications"])) + "}\n"
    t += "\n\\section{Languages}\n\\cvitem{}{" + esc(m["languages"]) + "}\n\n\\end{document}\n"
    return t


def compile_tex(base):
    if not shutil.which("lualatex"):
        print("WARN: lualatex not found; .tex written, not compiled")
        return None
    pdf = os.path.join(CV_DIR, base + ".pdf")
    if os.path.exists(pdf):
        os.remove(pdf)
    r = subprocess.run(["lualatex", "-interaction=nonstopmode", base + ".tex"], cwd=CV_DIR,
                       capture_output=True, text=True, timeout=180)
    pages = re.search(r"\((\d+) pages?", r.stdout)
    if not os.path.exists(pdf):
        print(f"WARN: compile failed, see cv/{base}.log")
        return None
    for ext in (".aux", ".out"):
        try:
            os.remove(os.path.join(CV_DIR, base + ext))
        except OSError:
            pass
    n = int(pages.group(1)) if pages else None
    if n != 2:
        print(f"WARN: PDF has {n} pages (target 2). Lower max_bullets in cv/master.json or trim the skill list.")
    return pdf


# ---------- tracker + archive (replaces /apply Step 6b) ----------
def update_tracker(company, role, fit, source, deadline, cv_file):
    today = datetime.date.today().isoformat()
    header, data = list(HEADER), []
    if os.path.exists(TRACKER):
        with open(TRACKER, newline="", encoding="utf-8") as f:
            lines = list(csv.reader(f))
        if lines:
            header, data = lines[0], lines[1:]
        if header[-1] != "deadline":
            header.append("deadline")
    ix = {h: i for i, h in enumerate(header)}
    for r in data:
        r += [""] * (len(header) - len(r))
    match = [r for r in data if r[ix["company"]].strip().lower() == company.lower()
             and r[ix["role"]].strip().lower() == role.lower()]
    open_rows = [r for r in match if r[ix["status"]].strip().lower() not in FINAL]
    if open_rows:
        r = open_rows[0]
        r[ix["cv_file"]], r[ix["fit_rating"]], r[ix["source"]] = cv_file, str(fit), source
        if deadline:
            r[ix["deadline"]] = deadline
        r[ix["notes"]] = (r[ix["notes"]] + "; redrafted").strip("; ")
        if r[ix["status"]].strip().lower() == "drafted":
            r[ix["date"]] = today
        action = "updated open row (status kept)"
    else:
        new = {"date": today, "company": company, "role": role, "status": "drafted", "fit_rating": str(fit),
               "cv_file": cv_file, "source": source, "deadline": deadline}
        data.append([clean_field(new.get(h, "")) for h in header])
        action = "appended new row" + (" (earlier application is closed, kept as is)" if match else "")
    tmp = TRACKER + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(data)
    os.replace(tmp, TRACKER)
    return action


def archive_posting(company, role, posting):
    # ASSUMPTION: confirm folder naming against "Subfolder naming" in documents/README.md
    d = os.path.join(ROOT, "documents", "applications", slug(company, role))
    path = os.path.join(d, "job_posting.md")
    if os.path.exists(path) or not posting:
        return path + (" (already existed, left as is)" if os.path.exists(path) else " (skipped, no text)")
    os.makedirs(d, exist_ok=True)
    open(path, "w", encoding="utf-8").write(posting)
    return path


# ---------- summaries ----------
SUMMARIES = os.path.join(ROOT, "job_scraper", "summaries.json")


def norm_key(url):
    """Normalize a posting URL for the summaries key: strip query/fragment and a trailing slash."""
    return url.split("?")[0].split("#")[0].rstrip("/")


def summary_key(company, role, source):
    if source and source.startswith("http"):
        return norm_key(source)
    return f"{company}|{role}".lower()


def load_summaries():
    try:
        with open(SUMMARIES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_summary(company, role, summary, source, force):
    """Persist a summary; never overwrite an existing one unless force=True."""
    data = load_summaries()
    key = summary_key(company, role, source)
    if key in data and not force:
        return data[key], False
    entry = {"company": company, "role": role, "summary": summary}
    data[key] = entry
    os.makedirs(os.path.dirname(SUMMARIES), exist_ok=True)
    with open(SUMMARIES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return entry, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("posting", nargs="?")
    ap.add_argument("--file"); ap.add_argument("--source")
    ap.add_argument("--company"); ap.add_argument("--role")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.summarize_only:
        posting, source = get_posting(a)
        if not posting.strip():
            die("no posting provided")
        res = summarize_llm(posting)
        company = (a.company or res.get("company", "")).strip()
        role = (a.role or res.get("role", "")).strip()
        summary = (res.get("summary") or "").strip()
        if not company or not role:
            die("could not determine company/role; pass --company and --role")
        _, wrote = save_summary(company, role, summary, source, a.force)
        if a.json:
            print(json.dumps({"company": company, "role": role, "summary": summary,
                              "tokens": res["_tokens"], "stored": wrote}, ensure_ascii=False))
        else:
            print(f"{company} | {role} | {summary}")
        return

    m = json.load(open(MASTER, encoding="utf-8"))
    posting, source = ("", "") if a.dry_run else get_posting(a)
    if not a.dry_run and not posting.strip():
        die("no posting provided")
    sel = dry_selection(m, a) if a.dry_run else call_llm(posting, m)
    company = (a.company or sel["company"]).strip()
    role = (a.role or sel["role"]).strip()
    if not company or not role:
        die("could not determine company/role; pass --company and --role")
    deadline = sel["deadline"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sel.get("deadline", "")) else ""
    fit = max(0, min(100, int(sel["fit_rating"])))
    base = "main_" + slug(company, role)
    open(os.path.join(CV_DIR, base + ".tex"), "w", encoding="utf-8").write(build_tex(m, sel))
    pdf = None if a.no_compile else compile_tex(base)
    cv_file = f"cv/{base}.tex"
    action = update_tracker(company, role, fit, clean_field(source), deadline, cv_file)
    arch = archive_posting(company, role, posting)
    summary = (sel.get("summary") or "").strip()
    if summary:
        save_summary(company, role, summary, source, a.force)
    if a.json:
        out = {"company": company, "role": role, "fit": fit, "gaps": sel["gaps"],
               "deadline": deadline, "files": [cv_file] + ([f"cv/{base}.pdf"] if pdf else []),
               "tracker": action, "summary": summary, "tokens": sel["_tokens"]}
        print(json.dumps(out, ensure_ascii=False))
        return
    print(f"{company} | {role} | fit {fit} | deadline {deadline or '-'} | tokens {sel['_tokens']}")
    print("gaps: " + ("; ".join(sel["gaps"]) or "none"))
    print(f"files: {cv_file}" + (f", cv/{base}.pdf" if pdf else ""))
    print(f"tracker: {action}\nposting: {arch}")


if __name__ == "__main__":
    main()
