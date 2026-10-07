export const SEARCH_URL = "https://www.getonbrd.com/api/v0/search/jobs"
export const COMPANY_URL = "https://www.getonbrd.com/api/v0/companies"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA = "Mozilla/5.0 (compatible; getonbrd-search-cli/1.0)"

/** Fetch JSON with exponential backoff on 429/5xx. Returns null on 404. */
export async function apiFetch(url: string): Promise<any> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "application/json",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(15000),
    })
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      const jitter = Math.floor(Math.random() * 500)
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response.json()
  }
  throw new Error("Request failed after max retries")
}

export interface JobResult {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  description: string | null
  deadline: string | null
  fit: string | null
  portal: string
  source: string
}

function cleanHtml(html: string): string {
  if (!html) return ""
  return html
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|ul|ol|div|h\d)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

/** In-memory cache of company-id → name, keyed by numeric company id. */
const companyNameCache = new Map<string, string>()

/** Best-effort fallback: derive a company name token from the job slug's tail. */
function companyFromSlug(id: string): string | null {
  if (!id) return null
  const parts = id.split("-")
  if (parts.length < 2) return null
  // Get on Board slugs end "-<company>-<location>"; the company token is the
  // second-to-last segment. (Segments themselves may already be hyphenated, so
  // this is only a fallback when the company endpoint is unreachable.)
  const last = parts[parts.length - 1]
  if (last === "remote" || last === "presencial" || last === "hibrido") {
    return parts[parts.length - 2]
  }
  return last
}

/** Resolve a company name from its numeric id, falling back to the slug token. */
async function resolveCompany(attrs: any, jobId: string): Promise<string | null> {
  const companyId = attrs?.company?.data?.id
  if (companyId == null) return companyFromSlug(jobId)
  const cached = companyNameCache.get(String(companyId))
  if (cached) return cached
  try {
    const json = await apiFetch(`${COMPANY_URL}/${companyId}`)
    const name = json?.data?.attributes?.name
    if (name) {
      companyNameCache.set(String(companyId), name)
      return name
    }
  } catch {
    // fall through to slug-derived name
  }
  return companyFromSlug(jobId)
}

/** Parse Get on Board JSON:API list payload. */
export async function parseJobs(json: any): Promise<JobResult[]> {
  if (!json || !Array.isArray(json.data)) return []
  const items = await Promise.all(json.data.map(async (item: any) => {
    const attrs = item.attributes || {}
    const companyName = await resolveCompany(attrs, item.id)

    let location = "Remote"
    if (!attrs.remote) {
      const countries = attrs.countries
      if (Array.isArray(countries)) {
        location = countries.join(", ")
      } else if (typeof countries === "string") {
        location = countries
      } else {
        location = "On-site"
      }
    }

    // Format publication date (Get on Board gives UNIX epoch time in seconds)
    let date: string | null = null
    if (attrs.published_at) {
      const d = new Date(attrs.published_at * 1000)
      if (!isNaN(d.getTime())) {
        date = d.toISOString().split("T")[0]
      }
    }

    // Direct posting URL
    const url = item.links?.public_url || `https://www.getonbrd.com/jobs/${item.id}`

    // Construct full descriptive texts
    const desc = cleanHtml(attrs.description || "")
    const projects = cleanHtml(attrs.projects || "")
    const benefits = cleanHtml(attrs.benefits || "")
    const requirements = cleanHtml(attrs.description_headline || "")

    const fullDescription = [
      desc,
      requirements ? `\n### Requirements\n${requirements}` : "",
      projects ? `\n### About the Company/Project\n${projects}` : "",
      benefits ? `\n### Benefits\n${benefits}` : ""
    ].filter(Boolean).join("\n")

    return {
      id: item.id,
      title: attrs.title || "(Untitled)",
      company: companyName,
      location,
      date,
      url,
      description: fullDescription || null,
      deadline: null, // Get on Board API doesn't provide explicit deadline date in standard list attributes
      fit: null,
      portal: "getonbrd-search",
      source: "cli"
    }
  }))
  return items
}
