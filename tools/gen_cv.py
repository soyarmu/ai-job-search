#!/usr/bin/env python3
"""Lean CV generator. Builds a LaTeX CV from cv/master.json, compiles it, then records
the tracker row and archives the posting. No LLM call, no API keys, no model choice:
content tailoring happens before this script runs.

The normal flow is a pre-evaluated selection written by the assistant (see
.claude/commands/cv.md); without --selection the script falls back to the default
selection (every skill and every bullet up to each job's max_bullets).

Usage:
  python3 tools/gen_cv.py selection.json                            (pre-evaluated selection)
  python3 tools/gen_cv.py "https://company.com/job/123" --selection selection.json
  python3 tools/gen_cv.py --file job.txt --source URL --selection selection.json
  python3 tools/gen_cv.py --dry-run --company X --role Y   (build/compile only; tracker and archive untouched)

Selection JSON fields: company, role, deadline, fit_rating, summary_id, summary,
skill_names, bullet_ids, gaps.
"""
import argparse, csv, datetime, hashlib, json, os, re, shutil, subprocess, sys, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CV_DIR = os.path.join(ROOT, "cv")
MASTER = os.path.join(CV_DIR, "master.json")
TRACKER = os.path.join(ROOT, "job_search_tracker.csv")
HEADER = ["date", "company", "sector", "role", "role_type", "channel", "status", "contact_person",
          "fit_rating", "notes", "cv_file", "cover_letter_file", "source", "deadline"]
# ASSUMPTION: align with "Tracker status vocabulary" in .claude/commands/outcome.md
FINAL = {"hired", "rejected", "no_response", "offer_declined", "withdrawn", "no response", "offer declined"}


def die(msg):
    sys.exit("ERROR: " + msg)


def _force_utf8_output():
    """Write UTF-8 whatever the host's default encoding is (see the same
    guard in tools/rank_state.py): a piped stdout on Windows defaults to the
    ANSI code page, so a non-ASCII company, role or summary would raise
    UnicodeEncodeError before the dashboard/CLI caller saw any output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")


def clean_field(s):
    """Tracker fields: no commas, quotes or line breaks."""
    return re.sub(r'[,"\r\n]+', " -" if "," in str(s) else " ", str(s)).strip()


def slug(company, role):
    """File/archive slug. Plain ASCII names keep the plain scheme; names that
    are non-ASCII or would exceed 72 chars get an md5 suffix so two different
    applications can never collide on the same filename or archive folder."""
    src = f"{company} {role}"
    base = re.sub(r"[^A-Za-z0-9]+", "_", src).strip("_")
    if len(base) <= 72 and not any(ord(c) > 127 for c in src):
        return base
    return base[:64].strip("_") + "_" + hashlib.md5(src.encode("utf-8")).hexdigest()[:8]


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


# ---------- selection (no LLM) ----------
def dry_selection(m, args):
    """Default content selection: every skill and every bullet, first summary, fit unrated.
    Used when no --selection JSON is provided (content tailoring is done out-of-band)."""
    return {"company": args.company or "", "role": args.role or "", "deadline": "", "fit_rating": 0,
            "summary_id": m["summaries"][0]["id"],
            "summary": "",
            "skill_names": [s for v in m["skills"].values() for s in v],
            "bullet_ids": [b["id"] for j in m["jobs"] for b in j["bullets"]], "gaps": []}


def load_selection(path):
    """Load a pre-evaluated selection JSON: {company, role, deadline, fit_rating,
    summary_id, summary, skill_names, bullet_ids, gaps}. Written by Claude/the user
    after evaluating the posting - no LLM runs inside this script."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
    summary = sums.get(sel.get("summary_id")) or m["summaries"][0]["text"]
    wanted = set(sel.get("skill_names") or [])
    skills = {g: [s for s in v if s in wanted] for g, v in m["skills"].items()}
    skills = {g: v for g, v in skills.items() if v}
    order = {b: i for i, b in enumerate(sel.get("bullet_ids") or [])}
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
    try:
        r = subprocess.run(["lualatex", "-interaction=nonstopmode", base + ".tex"], cwd=CV_DIR,
                           capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print(f"WARN: lualatex timed out after 180s; see cv/{base}.log")
        return None
    pages = re.search(r"\((\d+) pages?", r.stdout)
    if not os.path.exists(pdf):
        print(f"WARN: compile failed, see cv/{base}.log")
        return None
    for ext in (".aux", ".out", ".log"):
        try:
            os.remove(os.path.join(CV_DIR, base + ext))
        except OSError:
            pass
    n = int(pages.group(1)) if pages else None
    if n != 2:
        print(f"WARN: PDF has {n} pages (target 2). Lower max_bullets in cv/master.json or trim the skill list.")
    return pdf


def archive_pdf(base, pdf):
    """Copy the compiled PDF into cv/generated/YYYY-MM-DD/ so generated CVs are
    grouped by the day they were built. Returns the archived path, or None if
    there is no PDF to copy (compile skipped or failed)."""
    if not pdf:
        return None
    day = datetime.date.today().isoformat()
    dest_dir = os.path.join(CV_DIR, "generated", day)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(pdf))
    shutil.copyfile(pdf, dest)
    return os.path.relpath(dest, ROOT)


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
    missing = [c for c in ("company", "role", "status", "cv_file", "fit_rating", "source") if c not in header]
    if missing:
        die(f"tracker header missing columns {missing}; fix job_search_tracker.csv first")
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


# ---------- summaries persistence ----------
SUMMARIES = os.path.join(ROOT, "job_scraper", "summaries.json")


def norm_key(s):
    base = re.sub(r"[^a-z0-9]+", "", str(s).lower())
    if any(ord(c) > 127 for c in str(s)):
        base += "_" + hashlib.md5(str(s).encode("utf-8")).hexdigest()[:8]
    return base


def summary_key(company, role):
    return norm_key(company) + "|" + norm_key(role)


def load_summaries():
    if not os.path.exists(SUMMARIES):
        return {}
    try:
        with open(SUMMARIES, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def save_summary(company, role, summary):
    data = load_summaries()
    key = summary_key(company, role)
    data[key] = {"company": company, "role": role, "summary": summary}
    os.makedirs(os.path.dirname(SUMMARIES), exist_ok=True)
    with open(SUMMARIES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("posting", nargs="?")
    ap.add_argument("--file"); ap.add_argument("--source")
    ap.add_argument("--company"); ap.add_argument("--role")
    ap.add_argument("--selection", help="path to a pre-evaluated selection JSON (written by Claude/the user")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    _force_utf8_output()

    m = json.load(open(MASTER, encoding="utf-8"))
    posting, source = ("", "") if a.dry_run else get_posting(a)
    if not a.dry_run and not posting.strip():
        die("no posting provided")
    sel = load_selection(a.selection) if a.selection else dry_selection(m, a)
    company = (a.company or sel.get("company") or "").strip()
    role = (a.role or sel.get("role") or "").strip()
    if not company or not role:
        die("pass --company and --role")
    deadline = sel.get("deadline") or ""
    deadline = deadline if re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline) else ""
    try:
        fit = max(0, min(100, int(sel.get("fit_rating") or 0)))
    except (TypeError, ValueError):
        die("selection fit_rating must be an integer 0-100")
    summary = (sel.get("summary") or "").strip()
    base = "main_" + slug(company, role)
    open(os.path.join(CV_DIR, base + ".tex"), "w", encoding="utf-8").write(build_tex(m, sel))
    pdf = None if a.no_compile else compile_tex(base)
    gen_pdf = archive_pdf(base, pdf)
    cv_file = f"cv/{base}.tex"
    gaps = sel.get("gaps") or []
    files = [cv_file] + ([f"cv/{base}.pdf"] if pdf else []) + ([gen_pdf] if gen_pdf else [])
    if a.dry_run:
        # Build and compile only: the tracker row, posting archive and
        # summaries.json are the persistent records and stay untouched.
        if a.json:
            print(json.dumps({"dry_run": True, "company": company, "role": role, "fit": fit,
                              "gaps": gaps, "files": files},
                             ensure_ascii=False))
        else:
            print(f"dry-run: {company} | {role} | fit {fit} | tracker/archive untouched")
            print(f"files: " + ", ".join(files))
        return
    action = update_tracker(company, role, fit, clean_field(source), deadline, cv_file)
    arch = archive_posting(company, role, posting)
    if summary:
        save_summary(company, role, summary)
    if a.json:
        out = {"company": company, "role": role, "fit": fit, "gaps": gaps,
               "deadline": deadline, "files": files,
               "tracker": action, "summary": summary}
        print(json.dumps(out, ensure_ascii=False))
        return
    print(f"{company} | {role} | fit {fit} | deadline {deadline or '-'}")
    print(f"files: " + ", ".join(files))
    print(f"tracker: {action}\nposting: {arch}")


if __name__ == "__main__":
    main()
