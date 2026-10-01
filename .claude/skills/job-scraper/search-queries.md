# Search Queries for Job Scraper

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first. Shipped country-agnostic CLIs include `linkedin-search` and `freehire-search`. You do **not** need a matching `site:` line below for those CLIs to run.

The `site:` query templates in this file are the **WebSearch fallback** — for portals without a CLI, company career pages, or when a CLI fails.

**Language scope:** Queries are written in both English and Spanish (candidate works in both).

**Exclusions:** `-BairesDev` and `-Bairesdev` are appended to queries to prevent BairesDev job listings from populating search results.

## Search Sites

Primary:
- **linkedin.com/jobs** - LinkedIn job listings (Global Remote / US Remote / LATAM Remote / Colombia / Spain / Germany / UK)
- **wellfound.com/jobs** - High-growth startups & AI tech companies (Global / US / Europe)
- **getonbrd.com** - Leading tech and remote job board across LATAM & worldwide
- **remoteok.com** - Global remote developer jobs
- **weworkremotely.com** - Global remote engineering jobs
- **getmanfred.com** - Manfred (tech job board in Spain)
- **infojobs.net** - InfoJobs (Spain tech roles)
- **tecnoempleo.com** - Tecnoempleo (Spain specialized IT board)
- **dice.com** - Dice (US specialized tech board)

## Query Categories

### Priority 1: Senior Frontend Developer / Web UI Developer (React & TypeScript)

Core focus matching 5+ years of enterprise experience.

**English queries:**
```
site:linkedin.com/jobs "Senior Frontend Developer" React TypeScript Remote -BairesDev -Bairesdev
site:linkedin.com/jobs "Senior Web UI Developer" React TypeScript -BairesDev -Bairesdev
site:wellfound.com/jobs "Senior Frontend Engineer" React Next.js Remote -BairesDev
site:remoteok.com "Senior React Developer" TypeScript -BairesDev
site:weworkremotely.com "Frontend Developer" React Next.js -BairesDev
site:getmanfred.com React TypeScript Remote
site:dice.com "Senior Frontend Developer" React TypeScript Remote
```

**Spanish queries:**
```
site:getonbrd.com "Desarrollador Frontend Senior" React TypeScript
site:linkedin.com/jobs "Desarrollador Frontend Senior" Colombia OR España OR Remoto -BairesDev -Bairesdev
site:linkedin.com/jobs "Ingeniero Frontend" React TypeScript Remoto -BairesDev -Bairesdev
site:infojobs.net "Frontend Developer" React TypeScript Remoto
site:tecnoempleo.com "Frontend" React TypeScript Teletrabajo
```

### Priority 2: Agentic Engineer / AI Applications Engineer

Cutting-edge specialization in AI agents, MCP, and AWS Bedrock.

**English queries:**
```
site:linkedin.com/jobs "AI Engineer" "Agents" OR "Bedrock" OR "MCP" Remote -BairesDev
site:linkedin.com/jobs "Agentic Engineer" OR "AI Application Developer" Remote -BairesDev
site:wellfound.com/jobs "AI Engineer" React Python Remote -BairesDev
site:linkedin.com/jobs "Frontend Engineer" "AI" OR "LLM" Remote -BairesDev
site:getmanfred.com "AI" OR "Agents" Remote
```

**Spanish queries:**
```
site:getonbrd.com "Ingeniero AI" OR "Desarrollador AI" Remoto
site:linkedin.com/jobs "Ingeniero de Inteligencia Artificial" Remoto -BairesDev
```

### Priority 3: Fullstack Engineer (React / Next.js + Serverless / Node / Python)

Fullstack roles leveraging cloud serverless, microfrontends, and APIs.

**English queries:**
```
site:linkedin.com/jobs "Full Stack Developer" React Node AWS Remote -BairesDev
site:linkedin.com/jobs "Full Stack Engineer" TypeScript Python Serverless Remote -BairesDev
site:weworkremotely.com "Full Stack Engineer" React TypeScript -BairesDev
```

**Spanish queries:**
```
site:getonbrd.com "Desarrollador Full Stack" React TypeScript Remoto
site:linkedin.com/jobs "Desarrollador Full Stack" React Node Remoto -BairesDev
```

### Priority 4: Frontend Tech Lead / Software Engineering Lead

Leadership and architectural roles based on engineering lead experience at NTT DATA.

**English queries:**
```
site:linkedin.com/jobs "Frontend Tech Lead" React TypeScript Remote -BairesDev
site:linkedin.com/jobs "Software Engineering Lead" Frontend Remote -BairesDev
```

**Spanish queries:**
```
site:linkedin.com/jobs "Lider Tecnico Frontend" OR "Tech Lead Frontend" Colombia OR España OR Remoto -BairesDev
```

## Location Filter

- **Ideal:** Remote Spain, Remote Colombia, Remote US, Remote Germany, Remote UK, or Global Remote (hiring in these regions)
- **Acceptable:** Hybrid or on-site in Bogotá / Chía (Colombia), Madrid / Barcelona (Spain), London (UK), Berlin / Munich (Germany), or US tech hubs (with visa/remote contract support)
- **Too far / Excluded:** Non-remote roles outside Spain, Colombia, US, Germany, and UK; any Danish or other non-targeted regional portals

## Compensation Filter

- Minimum baseline: **$3,500 USD/month** or **11,000,000 COP**

## Language Filter

- Spanish (Native / C2)
- English (Advanced / B2 - Professional Working Proficiency)
- **Strict Constraint:** Only positions written in English or Spanish are allowed. Auto-exclude postings in German (even if in Germany), Danish, French, Portuguese, Japanese, or other non-English/non-Spanish languages, as well as roles requiring these as a mandatory language.

## Date Filter

Only include jobs posted within the last 14 days, or with an active application deadline.
