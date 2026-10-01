import { expect, test, describe } from "bun:test"
import { runSearch } from "../src/commands/search.ts"
import { runDetail } from "../src/commands/detail.ts"

describe("Get on Board CLI Live Smoke Tests", () => {
  test("runSearch should return 0 and retrieve React jobs", async () => {
    const code = await runSearch({
      query: "React",
      page: 1,
      limit: 2,
      format: "json",
    })
    expect(code).toBe(0)
  })

  test("runDetail should fail gracefully with exit code 1 for non-existent job ID", async () => {
    const code = await runDetail({
      id: "this-job-does-not-exist-12345",
      format: "json",
    })
    expect(code).toBe(1)
  })
})
