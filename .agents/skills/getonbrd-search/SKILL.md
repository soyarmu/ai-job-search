---
name: getonbrd-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs in Colombia, Chile, Peru,
  Mexico, Spain, or Latin America, or remote roles for LATAM/Spain. Triggers on tech
  and web developer roles (React, TypeScript, Frontend, Backend, Fullstack, AI, Mobile)
  on the Get on Board platform (getonbrd.com).
  Trigger phrases include: getonbrd, get on board, "jobs in Colombia", "trabajo remoto",
  "React jobs in LATAM", "frontend positions in Spain", "find tech jobs in Bogota".
context: fork
enabled: true
allowed-tools: Bash(bun run .agents/skills/getonbrd-search/cli/src/cli.ts *)
---

# Get on Board Search Skill

Search live tech and web development job listings from [Get on Board](https://www.getonbrd.com) — the leading tech job board in Colombia, Chile, Peru, Mexico, and Latin America.

No authentication or API keys required.

## When to use this skill

Invoke this skill when the user wants to:

- Search for tech jobs, developer openings, or AI roles in Colombia, Spain, or Latin America
- Find remote positions with LATAM/US/Europe timezone alignment
- Get full description, salary range, and requirements for a posting on Get on Board

## Commands

### Search jobs

```bash
bun run .agents/skills/getonbrd-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keyword search (job title, skill, company, country). Recommended.
- `--page <n>` — 1-indexed page. Default 1.
- `--limit, -n <n>` — cap total results returned (client-side).
- `--format json|table|plain` — default `json`.

### Fetch job detail

```bash
bun run .agents/skills/getonbrd-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the job slug from search results (e.g. `ingeniero-de-software-senior-checkr-santiago-e09f`). Returns description, requirements, deadline, remote mode, and apply link.

## Usage examples

```bash
# Frontend or React jobs in Colombia
bun run .agents/skills/getonbrd-search/cli/src/cli.ts search -q "React Colombia" --format table

# Remote software engineer roles
bun run .agents/skills/getonbrd-search/cli/src/cli.ts search -q "Software Engineer remoto" --limit 5 --format table

# Full details for a specific job
bun run .agents/skills/getonbrd-search/cli/src/cli.ts detail ingeniero-de-software-senior-checkr-santiago-e09f --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs/slugs to `detail` |
| `table` | Quick human-readable overviews and comparisons |
| `plain` | Reading a single job's full details |
