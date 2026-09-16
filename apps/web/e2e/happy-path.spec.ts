import { expect, test } from "@playwright/test";

test("index a repository and inspect a cited answer", async ({ page }) => {
  await page.route("http://localhost:8000/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/repositories/ingest")
      ? { job_id: "job", repository_id: "repo", status: "PENDING" }
      : path.endsWith("/ingestion/job")
        ? { job_id: "job", repository_id: "repo", status: "COMPLETED", ref: "main", files_seen: 1, files_indexed: 1, chunks_created: 1, error: null }
        : path.endsWith("/repositories/repo")
          ? { id: "repo", full_name: "owner/repo", default_branch: "main", latest_ref: "main", description: null, html_url: "https://github.com/owner/repo", latest_ingestion: "COMPLETED" }
          : path.endsWith("/repositories/repo/query")
            ? { answer: "Login is in auth.py [S1].", session_id: "session", citations: [{ id: "S1", source_id: "source", file_path: "src/auth.py", start_line: 1, end_line: 2, snippet: "def login():", score: 0.9, url: "https://github.com/owner/repo/blob/sha/src/auth.py#L1-L2" }], retrieval: { dense_candidates: 1, lexical_candidates: 1, fused_candidates: 1, reranked_candidates: 1, latency_ms: 2, sources: [] } }
            : path.endsWith("/sessions/session")
              ? { session_id: "session", repository_id: "repo", messages: [] }
              : { file_path: "src/auth.py", start_line: 1, end_line: 2, content: "def login():\n    pass" };
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await page.getByLabel("GitHub repository URL").fill("https://github.com/owner/repo");
  await page.getByRole("button", { name: "Index repository" }).click();
  await expect(page.getByText("Explore the codebase")).toBeVisible();
  await page.getByLabel("Ask a question about this repository").fill("Where is login?");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.getByText("Login is in auth.py [S1].")).toBeVisible();
  await page.getByRole("button", { name: /src\/auth.py/ }).click();
  await expect(page.getByText("def login():")).toBeVisible();
});
