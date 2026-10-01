# Get on Board API Reference

Public, unauthenticated REST API endpoint for Get on Board.

## Base URL
`https://www.getonbrd.com/api/v0`

## Endpoints

### 1. Job Search
- **Endpoint**: `/search/jobs`
- **Method**: `GET`
- **Query Parameters**:
  - `query` (string) - search terms (keywords, skills, country, city)
  - `page` (number) - page number (default 1)
  - `per_page` (number) - results per page (default 20, max 100)
- **Example**: `https://www.getonbrd.com/api/v0/search/jobs?query=react&per_page=10`

### 2. Job Detail
Get on Board uses a nested data structure inside search results. For a single job view, the detail endpoint is structured around the unique slug (e.g. `ingeniero-de-software-senior-checkr-santiago-e09f`).
- **Endpoint**: `/search/jobs` (since the search endpoint returns the full payload, we can use the same endpoint with the slug or fetch details from the public URL)
- Alternatively, we can construct the direct public URL for the job post: `https://www.getonbrd.com/jobs/<slug>` and parse it, or fetch the job list filtering by the slug.
- In practice, Get on Board search API returns the **full job payload including descriptions, requirements, and benefits directly in the search results**, which means a separate API detail endpoint isn't strictly necessary since search results are already fully populated! We can also parse the html of `https://www.getonbrd.com/jobs/<slug>` if needed.
