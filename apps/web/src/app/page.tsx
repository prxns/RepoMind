"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiFailure, Citation, HistoryMessage, Ingestion, QueryAnswer, Repository } from "@/lib/api";

const examples = [
  "Where is authentication implemented?",
  "Which tests cover user registration?",
  "How are API errors returned?",
];

function lastWorkspace(): { repositoryId: string | null; sessionId: string | null } {
  if (typeof window === "undefined") return { repositoryId: null, sessionId: null };
  try {
    const saved = localStorage.getItem("repomind:last");
    return saved ? JSON.parse(saved) : { repositoryId: null, sessionId: null };
  } catch {
    return { repositoryId: null, sessionId: null };
  }
}

function ErrorNotice({ message }: { message: string }) {
  return <div className="error" role="alert"><strong>Request failed</strong><span>{message}</span></div>;
}

function SourcePanel({ citation, repositoryId }: { citation: Citation; repositoryId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [content, setContent] = useState(citation.snippet);
  const [error, setError] = useState("");

  async function toggle() {
    if (!expanded) {
      try {
        const result = await api.source(repositoryId, citation.source_id, citation.start_line, citation.end_line);
        setContent(result.content);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not load source.");
      }
    }
    setExpanded(!expanded);
  }

  return <article className="source">
    <div className="source-heading">
      <button type="button" className="source-toggle" onClick={toggle} aria-expanded={expanded}>
        <span className="citation-id">{citation.id}</span>
        <span className="path">{citation.file_path}</span>
        <span className="line-range">L{citation.start_line}–{citation.end_line}</span>
      </button>
      <a href={citation.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${citation.file_path} on GitHub`}>Open ↗</a>
    </div>
    {error && <p className="inline-error">{error}</p>}
    {expanded && <pre className="source-code"><code>{content}</code></pre>}
  </article>;
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [repositoryId, setRepositoryId] = useState<string | null>(() => lastWorkspace().repositoryId);
  const [repository, setRepository] = useState<Repository | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [ingestion, setIngestion] = useState<Ingestion | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(() => lastWorkspace().sessionId);
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<QueryAnswer | null>(null);
  const [debug, setDebug] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!repositoryId) return;
    api.repository(repositoryId).then(setRepository).catch(() => {
      setRepositoryId(null);
      localStorage.removeItem("repomind:last");
    });
  }, [repositoryId]);

  useEffect(() => {
    if (!sessionId) return;
    api.history(sessionId).then(result => {
      setHistory(result.messages);
      const last = [...result.messages].reverse().find(message => message.role === "assistant");
      if (last) setAnswer({ answer: last.content, citations: last.citations,
        retrieval: last.retrieval, session_id: result.session_id });
    }).catch(() => setSessionId(null));
  }, [sessionId]);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    async function poll() {
      try {
        const result = await api.ingestion(jobId!);
        if (!active) return;
        setIngestion(result);
        if (result.status === "COMPLETED") {
          setJobId(null);
          setRepositoryId(result.repository_id);
          localStorage.setItem("repomind:last", JSON.stringify({ repositoryId: result.repository_id, sessionId: null }));
        }
        if (result.status === "FAILED") setJobId(null);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not read indexing status.");
      }
    }
    void poll();
    const timer = window.setInterval(poll, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [jobId]);

  async function startIngestion(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.ingest(url.trim(), ref.trim());
      setRepositoryId(null);
      setRepository(null);
      setSessionId(null);
      setHistory([]);
      setAnswer(null);
      setJobId(result.job_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start indexing.");
    } finally { setBusy(false); }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!repositoryId || !question.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.query(repositoryId, question.trim(), sessionId, debug);
      setAnswer(result);
      setHistory(items => [...items,
        { role: "user", content: question.trim(), citations: [], retrieval: result.retrieval, created_at: new Date().toISOString() },
        { role: "assistant", content: result.answer, citations: result.citations, retrieval: result.retrieval, created_at: new Date().toISOString() },
      ]);
      setSessionId(result.session_id);
      localStorage.setItem("repomind:last", JSON.stringify({ repositoryId, sessionId: result.session_id }));
      setQuestion("");
    } catch (cause) {
      setError(cause instanceof ApiFailure ? cause.message : "Could not answer the question.");
    } finally { setBusy(false); }
  }

  function reset() {
    setRepositoryId(null); setRepository(null); setJobId(null); setIngestion(null);
    setSessionId(null); setHistory([]); setAnswer(null); setError("");
    localStorage.removeItem("repomind:last");
  }

  const isIndexing = Boolean(jobId) || (ingestion && ingestion.status !== "COMPLETED" && ingestion.status !== "FAILED");
  const showWorkspace = repository && !isIndexing;

  return <div className="app-shell">
    <header className="topbar">
      <button type="button" className="brand" onClick={reset}>Repo<span>Mind</span></button>
      <div className="topbar-right">
        {repository && <span className="repo-label">{repository.full_name}<span className="separator">/</span>{repository.latest_ref || repository.default_branch}</span>}
        <span className="connection"><span className="connection-dot" />LOCAL WORKSPACE</span>
      </div>
    </header>

    {!showWorkspace && <main className="onboarding">
      <div className="eyebrow"><span className="eyebrow-line" /> REPOSITORY INTELLIGENCE</div>
      <h1>Understand a repository.</h1>
      <p className="intro">Index a public GitHub repository to search its source and ask questions with traceable file references.</p>
      <form className="onboard-form" onSubmit={startIngestion}>
        <label htmlFor="repo-url">GitHub repository URL</label>
        <input id="repo-url" type="url" required placeholder="https://github.com/owner/repository" value={url} onChange={event => setUrl(event.target.value)} />
        <label htmlFor="repo-ref">Branch or ref <span className="optional">optional</span></label>
        <input id="repo-ref" type="text" placeholder="Default branch" value={ref} onChange={event => setRef(event.target.value)} />
        <button type="submit" className="primary" disabled={busy || Boolean(jobId)}>{busy ? "Connecting…" : "Index repository"}<span>→</span></button>
      </form>
      <p className="helper">Source, docs, and common configuration files are indexed. Binary files, dependencies, and generated output are skipped.</p>
      {error && <ErrorNotice message={error} />}
      {ingestion && <section className="progress-panel" aria-live="polite">
        <div className="progress-top"><strong>Indexing progress</strong><span className="status-code">{ingestion.status}</span></div>
        <div className="progress-track"><span style={{ width: `${ingestion.status === "COMPLETED" ? 100 : ingestion.status === "FAILED" ? 100 : Math.min(90, 12 + ingestion.files_indexed / Math.max(ingestion.files_seen, 1) * 78)}%` }} /></div>
        <div className="progress-stats"><span>{ingestion.files_indexed} files indexed</span><span>{ingestion.chunks_created} chunks</span></div>
        {ingestion.error && <ErrorNotice message={ingestion.error.message} />}
      </section>}
    </main>}

    {showWorkspace && <div className="workspace">
      <aside className="sidebar" aria-label="Conversation history">
        <div className="sidebar-header"><span>WORKSPACE</span><button type="button" onClick={reset}>Change repo</button></div>
        <div className="repo-card"><span className="repo-avatar">{repository.full_name.charAt(0).toUpperCase()}</span><div><strong>{repository.full_name}</strong><small>{repository.description || "Public GitHub repository"}</small></div></div>
        <div className="sidebar-section"><span>SESSION</span><button type="button" onClick={() => { setSessionId(null); setHistory([]); setAnswer(null); }}>+ New question</button></div>
        <div className="history-list">{history.map((message, index) => message.role === "user" ? <button type="button" key={`${index}-${message.created_at}`} title={message.content} onClick={() => {
          const response = history[index + 1];
          if (response?.role === "assistant") setAnswer({ answer: response.content, citations: response.citations,
            retrieval: response.retrieval, session_id: sessionId || "" });
        }}>{message.content}</button> : null)}</div>
        <div className="sidebar-foot"><span className="connection-dot" /> Index ready</div>
      </aside>
      <main className="main-panel">
        <div className="panel-heading"><div><div className="eyebrow">ASK THE REPOSITORY</div><h1>Explore the codebase</h1></div><label className="debug-toggle"><input type="checkbox" checked={debug} onChange={event => setDebug(event.target.checked)} /> Retrieval details</label></div>
        <form className="question-form" onSubmit={ask}>
          <label htmlFor="question">Ask a question about this repository</label>
          <div className="composer"><textarea id="question" rows={3} maxLength={4000} value={question} onChange={event => setQuestion(event.target.value)} placeholder="Where is authentication implemented?" onKeyDown={event => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) event.currentTarget.form?.requestSubmit(); }} /><button className="primary" disabled={busy || question.trim().length < 3}>{busy ? "Working…" : "Ask question"}<span>↗</span></button></div>
          <span className="keyboard-hint">Ctrl/⌘ + Enter to submit</span>
        </form>
        {error && <ErrorNotice message={error} />}
        {!answer && history.length === 0 && <section className="suggestions"><h2>Start with a question</h2><p>Answers cite the indexed files used as evidence.</p><div>{examples.map(example => <button type="button" key={example} onClick={() => setQuestion(example)}>{example}<span>→</span></button>)}</div></section>}
        {answer && <section className="answer-section" aria-live="polite">
          <div className="section-label"><span>ANSWER</span><span>GROUNDED IN {answer.citations.length} SOURCE{answer.citations.length === 1 ? "" : "S"}</span></div>
          <div className="answer-text">{answer.answer}</div>
          <div className="sources-heading"><h2>Sources</h2><span>{answer.citations.length} references</span></div>
          {answer.citations.length ? answer.citations.map(citation => <SourcePanel key={citation.id} citation={citation} repositoryId={repositoryId!} />) : <p className="muted">No source citation was returned.</p>}
          {debug && <details className="retrieval-details"><summary>Retrieval details</summary><dl><div><dt>Dense candidates</dt><dd>{answer.retrieval.dense_candidates}</dd></div><div><dt>Lexical candidates</dt><dd>{answer.retrieval.lexical_candidates}</dd></div><div><dt>Fused candidates</dt><dd>{answer.retrieval.fused_candidates}</dd></div><div><dt>Reranked candidates</dt><dd>{answer.retrieval.reranked_candidates}</dd></div><div><dt>Latency</dt><dd>{answer.retrieval.latency_ms} ms</dd></div></dl></details>}
        </section>}
      </main>
    </div>}
    <footer className="footer"><span>RepoMind</span><span>Evidence before eloquence.</span></footer>
  </div>;
}
