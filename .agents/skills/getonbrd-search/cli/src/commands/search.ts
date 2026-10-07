import { apiFetch, SEARCH_URL, parseJobs, type JobResult } from "../helpers.ts"

export interface SearchOpts {
  query?: string
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const params = new URLSearchParams()
    if (opts.query) {
      params.append("query", opts.query)
    }
    params.append("page", String(opts.page))
    params.append("per_page", "100") // always request maximum per page to filter locally

    const url = `${SEARCH_URL}?${params.toString()}`
    const json = await apiFetch(url)

    if (!json) {
      if (opts.format === "json") {
        process.stdout.write(JSON.stringify({ meta: { count: 0, page: opts.page }, results: [] }, null, 2) + "\n")
      } else {
        process.stdout.write("No jobs found.\n")
      }
      return 0
    }

    let results = await parseJobs(json)

    if (opts.limit && opts.limit > 0) {
      results = results.slice(0, opts.limit)
    }

    if (opts.format === "json") {
      const output = {
        meta: {
          count: results.length,
          page: opts.page,
        },
        results: results.map(r => ({
          id: r.id,
          title: r.title,
          company: r.company,
          location: r.location,
          date: r.date,
          url: r.url,
        })),
      }
      process.stdout.write(JSON.stringify(output, null, 2) + "\n")
    } else if (opts.format === "table") {
      if (results.length === 0) {
        process.stdout.write("No results found.\n")
        return 0
      }
      // Print simple table
      const header = `| ID | Title | Company | Location | Date | URL |\n|---|---|---|---|---|---|`
      const rows = results.map(r =>
        `| ${r.id} | ${r.title} | ${r.company || "-"} | ${r.location || "-"} | ${r.date || "-"} | ${r.url} |`
      )
      process.stdout.write(`${header}\n${rows.join("\n")}\n`)
    } else {
      // plain text output
      if (results.length === 0) {
        process.stdout.write("No results found.\n")
        return 0
      }
      for (const r of results) {
        process.stdout.write(`ID: ${r.id}\nTitle: ${r.title}\nCompany: ${r.company || "-"}\nLocation: ${r.location || "-"}\nDate: ${r.date || "-"}\nURL: ${r.url}\n${"-".repeat(40)}\n`)
      }
    }

    return 0
  } catch (err: any) {
    process.stderr.write(JSON.stringify({ error: err.message, code: "SEARCH_FAILED" }) + "\n")
    return 1
  }
}
