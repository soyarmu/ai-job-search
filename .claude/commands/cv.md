---
description: Generate a tailored CV from a job posting (assistant tailors it, the script builds it)
argument-hint: <job URL or pasted posting text>
---

Tailor and generate the CV. You (the assistant) evaluate the posting and select the content; `tools/gen_cv.py` only builds, compiles, and records. There is no model choice and no API key anywhere in this flow.

1. Get the posting text:
   - If `$ARGUMENTS` is pasted text, write it verbatim to `job_scraper/tmp_posting.txt` with the Write tool.
   - If `$ARGUMENTS` is a URL, fetch it (WebFetch; on 403 follow the escalation order in `.claude/skills/job-application-assistant/09-web-research.md`, e.g. curl with a browser User-Agent), strip the HTML, and write the plain text to `job_scraper/tmp_posting.txt`.
   - If the URL cannot be fetched at all, ask the user to paste the posting text and use that.
2. Evaluate and tailor. Read `cv/master.json`, then write `job_scraper/selection.json` with these fields:
   - `company`, `role` — exactly as the posting names them.
   - `deadline` — YYYY-MM-DD only if the posting states one, else `""`.
   - `fit_rating` — integer 0-100 (round the weighted overall score from `.claude/skills/job-application-assistant/04-job-evaluation.md`).
   - `summary_id` — one existing summary id from `cv/master.json`.
   - `summary` — neutral one-line role description, max 40 words: what it does, main stack, seniority, location/remote. No hype.
   - `skill_names` — exact skill names from the catalog groups, only ones the posting calls for.
   - `bullet_ids` — bullet ids from the catalog that match the posting (the script caps each job at `max_bullets` and enforces `min_bullets`).
   - `gaps` — posting requirements the catalog does not support, max 5 short phrases.
   Never invent, reword, or add experience: only ids and skill names that exist in `cv/master.json`.
3. Run: `python3 tools/gen_cv.py --file job_scraper/tmp_posting.txt --selection job_scraper/selection.json`
   If the posting came from a URL, add `--source "<that URL>"` so the tracker stores it.
4. Show the script output as is (company, role, fit, deadline, files, tracker action). If the script warns the PDF is not 2 pages, report it and rerun after lowering `max_bullets` in `cv/master.json`.

Rules: do not read or edit the generated CV, do not recompile, do not research the company, do not write a cover letter, do not touch `job_search_tracker.csv` (the script owns it). If the user wants changes, they edit `cv/master.json` or ask explicitly.
