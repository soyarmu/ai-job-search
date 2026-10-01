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

    // Query Get on Board API using the ID as a keyword query to locate the specific job
    const params = new URLSearchParams()
    params.append("query", id)
    params.append("page", "1")
    params.append("per_page", "10")

    const url = `${SEARCH_URL}?${params.toString()}`
    const json = await apiFetch(url)

    if (!json) {
      process.stderr.write(JSON.stringify({ error: `Job with ID '${id}' not found`, code: "NOT_FOUND" }) + "\n")
      return 1
    }

    const results = parseJobs(json)
    const job = results.find(r => r.id === id)

    if (!job) {
      process.stderr.write(JSON.stringify({ error: `Job with ID '${id}' not found in search results`, code: "NOT_FOUND" }) + "\n")
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
