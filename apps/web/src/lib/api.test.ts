import { afterEach, expect, test, vi } from "vitest";
import { api, ApiFailure } from "./api";

afterEach(() => vi.unstubAllGlobals());

test("ingest sends the URL and optional ref to the repository endpoint", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ job_id: "job", repository_id: "repo", status: "PENDING" }) });
  vi.stubGlobal("fetch", fetchMock);
  const result = await api.ingest("https://github.com/o/r", "main");
  expect(result.job_id).toBe("job");
  expect(fetchMock.mock.calls[0][0]).toContain("/repositories/ingest");
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ url: "https://github.com/o/r", ref: "main" });
});

test("structured API errors are shown to the caller", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: {
    code: "NOT_INDEXED", message: "Index first.", retryable: false,
  } }) }));
  await expect(api.query("repo", "Where is login?", null, false)).rejects.toEqual(new ApiFailure("Index first.", "NOT_INDEXED", false));
});
