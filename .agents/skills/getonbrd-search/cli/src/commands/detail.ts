import { apiFetch, SEARCH_URL, parseJobs, type JobResult } from "../helpers.ts"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  try {
    // Extract ID/slug from URL if full URL is passed
    let id = opts.id
    if (id.includes("getonbrd.com/jobs/")) {
      const match = id.match(/\/jobs\/([^?#/\s]+)/)
      if (match) id = match[1]
    }

    // Get on Board's search index does not match on the posting slug, so query by
    // distinctive tokens taken from the slug (company name first, then other terms)
    // and locate the exact posting by its id locally.
    const tokens = id.split("-").filter(t => t.length > 2)
    // Try the segment most likely to be the company/employer first, then any others.
    const candidateQueries = [tokens[tokens.length - 2] || tokens[tokens.length - 1], ...tokens.slice(0, -2).reverse()].filter(Boolean)

    let job: JobResult | undefined
    for (const q of candidateQueries) {
      const params = new URLSearchParams()
      params.append("query", q)
      params.append("page", "1")
      params.append("per_page", "50")

      const url = `${SEARCH_URL}?${params.toString()}`
      const json = await apiFetch(url)
      if (!json) continue

      const results = await parseJobs(json)
      job = results.find(r => r.id === id)
      if (job) break
    }

    if (!job) {
      process.stderr.write(JSON.stringify({ error: `Job with ID '${id}' not found`, code: "NOT_FOUND" }) + "\n")
      return 1
    }

    if (opts.format === "json") {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    } else {
      process.stdout.write(`TITLE: ${job.title}
COMPANY: ${job.company || "-"}
LOCATION: ${job.location || "-"}
DATE: ${job.date || "-"}
URL: ${job.url}

DESCRIPTION:
${job.description || "(No description)"}
`)
    }

    return 0
  } catch (err: any) {
    process.stderr.write(JSON.stringify({ error: err.message, code: "DETAIL_FAILED" }) + "\n")
    return 1
  }
}
