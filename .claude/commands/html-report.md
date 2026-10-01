# /html-report - Generate Application Tracker Dashboard

Generate a self-contained HTML dashboard from `job_search_tracker.csv`, `job_scraper/seen_jobs.json`, and the application archives under `documents/applications/`. The output is a single `.html` file — no server, no dependencies — that can be opened directly in a browser.

## Step 0: Parse Arguments

- No argument → output to `reports/application-dashboard.html`
- A path argument (e.g. `/html-report ~/Desktop/report.html`) → use that path
- `--open` flag → after writing, tell the user to open the file (cannot open a browser directly)

Create `reports/` if it does not exist.

---

## Step 1: Collect Data

Read in parallel:

1. **`job_search_tracker.csv`** — Parse every row into a record with fields:
   `date`, `company`, `sector`, `role`, `role_type`, `channel`, `status`, `contact_person`, `fit_rating`, `notes`, `cv_file`, `cover_letter_file`, `source`, `deadline`

   Rows written before `deadline` existed have thirteen fields and no fourteenth value. Treat the missing field as empty - never drop the row, and never infer a deadline from its `date`.

2. **`job_scraper/seen_jobs.json`** — Load if present (default to empty list if missing). Parse each entry from the `seen` dictionary:
   `title`, `company`, `url`, `first_seen`, `posted_date`, `deadline`, `fit`, `status` (new/skipped/ranked/expired), `portal`, `source`, `rank_score`, `rank_verdict`, `strengths`, `gaps`.

3. **`documents/applications/*/outcome.md`** — Read outcome files to extract the exact interview stages reached (checkboxes) and any notes.

**Merging & Linking Logic:**
Match tracker CSV rows and `seen_jobs.json` entries:
- Match by `source` (CSV) matching `url` (JSON) case-insensitively, ignoring trailing slashes.
- Or fuzzy match by lowercase, punctuation-stripped `company` + `role` (CSV) against `company` + `title` (JSON).
- When matched, combine properties:
  - `date_found` = JSON `first_seen` or `posted_date` (fall back to CSV `date` if absent)
  - `date_applied` = CSV `date`
  - `rank_score` = JSON `rank_score` (if present)
  - `rank_verdict` = JSON `rank_verdict`
  - `strengths` = JSON `strengths`
  - `gaps` = JSON `gaps`
- **CV / Cover Letter Existence check**:
  - `has_cv` is true if the CSV `cv_file` is non-empty, OR if a file matching `cv/main_<company>_<role>.*` or `documents/applications/<company>_<role>/cv.*` exists on disk.
  - `has_cl` is true if the CSV `cover_letter_file` is non-empty, OR if a file matching `cover_letters/cover_<company>_<role>.*` or `documents/applications/<company>_<role>/cover_letter.*` exists on disk.

Status normalisation — map tracker values to six canonical buckets before computing stats:
- `drafted` → **Drafted** (documents written by `/apply`, not yet submitted)
- `applied` → **Active** (resume submitted, no further signal)
- `interview` → **Interview**
- `offer` → **Offer**
- `hired` → **Hired**
- `rejected` / `no_response` / `no response` / `offer_declined` / `offer declined` / `withdrawn` → **Rejected/Closed**
- anything else → **Rejected/Closed**, and name the unrecognised value once in the status breakdown — matching is case-insensitive

The bucket map tolerates the legacy space spellings on read so nothing written before the canonical forms were locked drops out of the stats; the **Tracker status vocabulary** in `/outcome` is the authoritative set.

---

## Step 2: Compute Summary Stats

From the normalised data compute:

**Drafted rows and unapplied opportunities are excluded from every statistic below** — they were never submitted. Report the Drafted count and unapplied counts on their own, and include Drafted only in the status breakdown.

- **Total applications**
- **By status bucket:** count per bucket
- **By sector:** count per unique sector value
- **By channel:** portal vs online vs referral vs other
- **By year/season:** group by the `date` field (which may be a year like `2025` or a full date)
- **Funnel rates:** what % progressed past resume screen (reached Interview or beyond). Compute stage-reached from history, not current status: an application counts as having reached a stage when its current status implies it **or** its merged `outcome.md` stage checkboxes show the stage was reached. Current status alone undercounts.
- **Rejection rate:** true rejections (`rejected`, `no_response`) ÷ applications with a final outcome. `offer_declined` and `withdrawn` are not rejections and stay out of the numerator; Interview and Offer rows are still unresolved, so they stay out of the denominator along with Active.

---

## Step 3: Generate the HTML

Write a single self-contained HTML file with inline CSS and JS. Draw the charts as hand-generated inline SVG. No Chart.js, no CDN, no external dependencies.

**Escaping (required):** HTML-escape every CSV/outcome-file/JSON value (`&` `<` `>` `"` `'`) before interpolating it into the page.

### Layout

```
┌─────────────────────────────────────────────┐
│  🔍 Job Search Dashboard    Generated: DATE  │
├──────┬──────┬──────┬──────┬──────┬───────────┤
│Sent  │Draft │Active│Inter-│Offer │Opportu-   │  ← stat cards
│  N   │  N   │  N   │view N│  N   │nities N   │
├──────┴──────┴──────┴──────┴──────┴───────────┤
│  Status breakdown (doughnut) │ By sector (bar)│  ← charts row
├─────────────────────────────────────────────  ┤
│  By channel (bar)  │  Funnel (horizontal bar) │  ← charts row
├──────────────────────────────────────────────  ┤
│  Tabs: [🎯 Applications] [✨ Opportunities]   │  ← Interactive Tabs
│  [📦 Archived] [🌐 All Entries]               │
├──────────────────────────────────────────────  ┤
│  Applications  [Status ▾] [Sector ▾] [🔍 ...]│  ← table with filters
│  Date Found | Date Applied | CV | CL | Company | Role | Status | ...
│  ...                                          │
└───────────────────────────────────────────────┘
```

### Design spec

- **Colour palette:**
  - Drafted: `#64748b` (slate)
  - Active: `#3b82f6` (blue)
  - Interview: `#f59e0b` (amber)
  - Offer: `#8b5cf6` (purple)
  - Hired: `#22c55e` (green)
  - Rejected/Closed: `#ef4444` (red)
- **Font:** system-ui stack, no web fonts
- **Stat cards:** white background, subtle shadow, large bold number, label below, left border in status colour
- **Charts:** contained in a 2-column grid on wide screens, stacked on narrow
- **Interactive Tabs:** Let the user toggle between Active Applications, Shortlisted Opportunities (status `ranked`/`new` in seen_jobs.json, not in tracker), Archived & Closed (resolved applications + skipped/expired opportunities), and All Entries.
- **Table:**
  - Alternating row shading
  - Clickable row that **toggles open an expandable detailed accordion drawer**:
    - **Match Score / Fit**: Showing `rank_score`, `rank_verdict`, and specific lists of `strengths` and `gaps` from `seen_jobs.json`.
    - **Key Requirements**: From `seen_jobs.json`.
    - **Referral Helpers**: Actionable search links for LinkedIn:
      - *Recruiter search*: `https://www.linkedin.com/search/results/people/?keywords=<Company>+recruiter`
      - *Peer search*: `https://www.linkedin.com/search/results/people/?keywords=<Company>+<Role+Keyword>`
    - **Local Documents**: Clickable local file paths for easy access.
    - **Outcome Details**: Full outcome history and notes.
  - CV/CL columns use high-visibility interactive badges (📄 checkmark if exists, ❌ if missing).
  - `Source` column renders as a hyperlink if the value is a URL (starts with `http`).
  - Empty cells render as `—`.
  - Client-side filter: text input (Company/Role/Sector/Notes), status dropdown, sector dropdown (all combine via AND).
  - Sorted newest-first by default (by `date` descending, then alphabetically by company).
- **Responsive:** usable at 900px+, not broken below that
- **Footer:** "Generated by Claude Code · ai-job-search · {ISO date}"

### Charts (inline SVG)

1. **Status doughnut** — slices for each status bucket.
2. **By sector bar** (horizontal) — company count per sector.
3. **By channel bar** — online / referral / other.
4. **Application funnel** (horizontal bar) — Applied → Interview → Offer → Hired.

### Table: columns to include

`Date` · `Deadline` · `Company` · `Role` · `Sector` · `Channel` · `Status` · `Notes` (truncated to 80 chars with `title` tooltip for full text) · `Source` (link or `—`)

Columns with only empty values across all rows may be omitted.

---

## Step 4: Write and Confirm

Write the complete HTML to the output path using the Write tool.

Then present:

> **Dashboard generated:** `<output path>`
>
> Open it in any browser — no server needed.
>
> **Summary:**
> - Applications sent: N · drafted, not yet sent: N
> - Active: N · Interview: N · Hired: N · Rejected/Closed: N
> - Opportunities: N
> - Funnel: N% progressed past resume screen
>
> Re-run `/html-report` any time after adding new entries via `/apply` or `/outcome` to refresh the dashboard.

---

## Design Principles

- **Self-contained.** One file, fully offline — charts are inline SVG, no CDN or external requests of any kind.
- **Data-only.** This command reads and renders; it never writes to the tracker or archive.
- **Idempotent.** Re-running overwrites the previous report at the same path — no accumulation.
- **Graceful on sparse data.** Charts render correctly for small N; the table is the primary value.
- **No fabrication.** Every number in the report comes directly from the CSV or JSON/outcome files.
