---
description: Generate a tailored CV from a job posting (lean: one LLM call, one compile)
argument-hint: <job URL or pasted posting text>
---

Generate the CV by running the script. Do nothing else.

1. If `$ARGUMENTS` is a URL, run: `python3 tools/gen_cv.py "$ARGUMENTS"`
2. If it is pasted text, write it verbatim to `job_scraper/tmp_posting.txt` with the Write tool, then run: `python3 tools/gen_cv.py --file job_scraper/tmp_posting.txt`
3. If the script fails because the URL could not be fetched, ask the user to paste the posting text and use step 2.
4. Show the script output as is (company, role, fit, gaps, files, tracker action).

Rules: do not read or edit the generated CV, do not recompile, do not research the company, do not write a cover letter, do not touch `job_search_tracker.csv` (the script owns it). If the user wants changes, they edit `cv/master.json` or ask explicitly.
