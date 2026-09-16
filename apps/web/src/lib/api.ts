export type Citation = {
  id: string;
  source_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  snippet: string;
  score: number;
  url: string;
};

export type Ingestion = {
  job_id: string;
  repository_id: string;
  status: "PENDING" | "FETCHING" | "PARSING" | "EMBEDDING" | "INDEXING" | "COMPLETED" | "FAILED";
  ref: string;
  files_seen: number;
  files_indexed: number;
  chunks_created: number;
  error: { code: string; message: string } | null;
};

export type Repository = {
  id: string;
  full_name: string;
  default_branch: string;
  description: string | null;
  html_url: string;
  latest_ingestion: string | null;
  latest_ref: string | null;
};

export type QueryAnswer = {
  answer: string;
  citations: Citation[];
  retrieval: {
    dense_candidates: number;
    lexical_candidates: number;
    fused_candidates: number;
    reranked_candidates: number;
    latency_ms: number;
    sources: { path: string; start_line: number; end_line: number; score: number }[];
  };
  session_id: string;
};

export type HistoryMessage = {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  retrieval: QueryAnswer["retrieval"];
  created_at: string;
};

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiFailure extends Error {
  constructor(message: string, public code: string, public retryable: boolean) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiFailure("The API is unreachable. Check that the local server is running.", "NETWORK_ERROR", true);
  }
  const data = await response.json();
  if (!response.ok) {
    throw new ApiFailure(data.error?.message ?? "Request failed.", data.error?.code ?? "UNKNOWN", data.error?.retryable ?? false);
  }
  return data as T;
}

export const api = {
  ingest: (url: string, ref: string) => call<{ job_id: string; repository_id: string; status: string }>(
    "/repositories/ingest", { method: "POST", body: JSON.stringify({ url, ref: ref || null }) }),
  ingestion: (id: string) => call<Ingestion>(`/ingestion/${id}`),
  repository: (id: string) => call<Repository>(`/repositories/${id}`),
  query: (id: string, question: string, sessionId: string | null, debug: boolean) => call<QueryAnswer>(
    `/repositories/${id}/query`, { method: "POST", body: JSON.stringify({ question, session_id: sessionId, debug }) }),
  history: (id: string) => call<{ session_id: string; repository_id: string; messages: HistoryMessage[] }>(`/sessions/${id}`),
  source: (repositoryId: string, sourceId: string, start: number, end: number) => call<{
    file_path: string; content: string; start_line: number; end_line: number;
  }>(`/repositories/${repositoryId}/sources/${sourceId}?start_line=${start}&end_line=${end}`),
};
