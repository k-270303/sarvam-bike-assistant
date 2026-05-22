"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import {
  ApiClientError,
  checkBackendConnection,
  createSession,
  getApiBaseUrl,
  getUploadApiBaseUrl,
  transcribeAudio,
  troubleshoot,
  troubleshootWithImage,
  uploadManuals,
} from "@/lib/api";
import type { TroubleshootResponse } from "@/types/api";

const EXAMPLES = [
  "For Pulsar N160, what is the spark plug gap?",
  "My TVS Sport will not start because I left the stand down. What should I do?",
  "My Splendor feels weak and is not picking up speed properly.",
  "How can I modify my bike to make it faster?",
];

function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function friendlyError(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string>("");
  const [manualFiles, setManualFiles] = useState<File[]>([]);
  const [documents, setDocuments] = useState<string[]>([]);
  const [pagesProcessed, setPagesProcessed] = useState(0);
  const [chunksIndexed, setChunksIndexed] = useState(0);
  const [uploadWarnings, setUploadWarnings] = useState<string[]>([]);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string>("");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<TroubleshootResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [backendCheck, setBackendCheck] = useState<string>("");
  const [isCreatingSession, setIsCreatingSession] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isAsking, setIsAsking] = useState(false);

  const manualsReady = documents.length > 0 && chunksIndexed > 0;
  const totalManualSize = useMemo(
    () => manualFiles.reduce((total, file) => total + file.size, 0),
    [manualFiles],
  );

  useEffect(() => {
    let isMounted = true;
    async function init() {
      try {
        const payload = await createSession();
        if (isMounted) setSessionId(payload.session_id);
      } catch (err) {
        if (isMounted) setError(friendlyError(err));
      } finally {
        if (isMounted) setIsCreatingSession(false);
      }
    }
    init();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!imageFile) {
      setImagePreview("");
      return;
    }
    const url = URL.createObjectURL(imageFile);
    setImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [imageFile]);

  function handleManualChange(event: ChangeEvent<HTMLInputElement>) {
    setManualFiles(Array.from(event.target.files ?? []));
  }

  function handleAudioChange(event: ChangeEvent<HTMLInputElement>) {
    setAudioFile(event.target.files?.[0] ?? null);
  }

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    setImageFile(event.target.files?.[0] ?? null);
  }

  async function handleUpload() {
    if (!sessionId || manualFiles.length === 0) return;
    setError("");
    setResult(null);
    setIsUploading(true);
    try {
      const payload = await uploadManuals(sessionId, manualFiles);
      setDocuments(payload.documents);
      setPagesProcessed(payload.pages_processed);
      setChunksIndexed(payload.chunks_indexed);
      setUploadWarnings(payload.warnings ?? []);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsUploading(false);
    }
  }

  async function handleTranscribe() {
    if (!audioFile) return;
    setError("");
    setIsTranscribing(true);
    try {
      const payload = await transcribeAudio(audioFile);
      setQuery(payload.transcript);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsTranscribing(false);
    }
  }

  async function handleAsk() {
    if (!sessionId || !manualsReady || !query.trim()) return;
    setError("");
    setResult(null);
    setIsAsking(true);
    try {
      const payload = imageFile
        ? await troubleshootWithImage(sessionId, query, imageFile)
        : await troubleshoot(sessionId, query);
      setResult(payload);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsAsking(false);
    }
  }

  async function handleBackendCheck() {
    setError("");
    setBackendCheck("Running raw backend diagnostics…");

    async function probe(path: string, init?: RequestInit): Promise<{ line: string; body: string; ok: boolean }> {
      try {
        const response = await fetch(path, {
          cache: "no-store",
          ...init,
          headers: {
            Accept: "application/json,text/plain,*/*",
            ...(init?.headers ?? {}),
          },
        });
        const contentType = response.headers.get("content-type") ?? "unknown";
        const text = await response.text();
        return {
          ok: response.ok,
          body: text,
          line: `${path} → ${response.status} ${response.statusText}; ${contentType}; ${text.slice(0, 180)}`,
        };
      } catch (err) {
        const reason = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
        return { ok: false, body: "", line: `${path} → browser fetch failed; ${reason}` };
      }
    }

    const health = await probe("/backend/health");
    const session = await probe("/backend/sessions", { method: "POST" });
    setBackendCheck(`${health.line}
${session.line}`);

    if (session.ok) {
      try {
        const parsed = JSON.parse(session.body) as { session_id?: string };
        if (parsed.session_id) {
          setSessionId(parsed.session_id);
          setError("");
        }
      } catch {
        // Raw diagnostic already shows the unexpected body.
      }
    }
  }

  async function handleFreshSession() {
    setError("");
    setResult(null);
    setDocuments([]);
    setPagesProcessed(0);
    setChunksIndexed(0);
    setUploadWarnings([]);
    setManualFiles([]);
    setAudioFile(null);
    setImageFile(null);
    setQuery("");
    setIsCreatingSession(true);
    try {
      const payload = await createSession();
      setSessionId(payload.session_id);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setIsCreatingSession(false);
    }
  }

  const askDisabled = !manualsReady || !query.trim() || isAsking || isCreatingSession;

  return (
    <main className="appShell">
      <header className="topBar">
        <div className="brand">
          <div className="logoMark">⚙</div>
          <span>Bike Troubleshooting Assistant</span>
        </div>
        <div className="topMeta">
          <span className={manualsReady ? "pill pillReady" : "pill"}>
            {manualsReady ? "Manual index ready" : "Waiting for manuals"}
          </span>
          <span className="pill">Backend {getApiBaseUrl().replace(/^https?:\/\//, "")}</span>
          <span className="pill">Uploads {getUploadApiBaseUrl().replace(/^https?:\/\//, "")}</span>
          <span className="pill">Session {sessionId ? `${sessionId.slice(0, 8)}…` : "starting…"}</span>
        </div>
      </header>

      <section className="hero">
        <div className="heroCard">
          <div>
            <h1>Reliable bike troubleshooting from uploaded manuals.</h1>
            <p>
              Upload one or more owner, service, or user manuals. Ask with text, voice, or an image. The assistant answers only when retrieved manual evidence supports it.
            </p>
          </div>
          <div className="statsGrid">
            <Stat label="Manual status" value={manualsReady ? "Ready" : "Waiting"} />
            <Stat label="Manuals" value={String(documents.length)} />
            <Stat label="Pages" value={String(pagesProcessed)} />
            <Stat label="Chunks" value={String(chunksIndexed)} />
          </div>
        </div>
        <aside className="guardrailPanel heroCard">
          <h2>Guardrail contract</h2>
          <ol>
            <li>Understand ambiguity before retrieval.</li>
            <li>Retrieve relevant manual excerpts.</li>
            <li>Answer only with evidence.</li>
            <li>Cite exact source text.</li>
            <li>Refuse or ask when unsupported.</li>
          </ol>
          <div className="notice noticeInfo" style={{ marginTop: 18 }}>
            Vision observes. Manuals diagnose. The LLM explains only from retrieved evidence.
          </div>
        </aside>
      </section>

      {error ? <div className="notice noticeError" style={{ marginBottom: 18 }}>{error}</div> : null}
      {backendCheck ? (
        <pre className="notice noticeInfo" style={{ marginBottom: 18, whiteSpace: "pre-wrap" }}>{backendCheck}</pre>
      ) : null}

      <section className="grid">
        <aside>
          <div className="panel stack">
            <div className="row spaceBetween">
              <h2>1. Upload manuals</h2>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn btnSecondary" onClick={handleBackendCheck} disabled={isCreatingSession || isUploading}>
                  Check backend
                </button>
                <button className="btn btnSecondary" onClick={handleFreshSession} disabled={isCreatingSession || isUploading}>
                  Fresh session
                </button>
              </div>
            </div>
            <p className="helper">
              PDFs are processed for this backend session only. They are not stored as durable app data.
            </p>
            <input className="fileInput" type="file" accept="application/pdf" multiple onChange={handleManualChange} />
            {manualFiles.length > 0 ? (
              <div className="helper">
                Selected {manualFiles.length} PDF(s), {formatBytes(totalManualSize)} total.
              </div>
            ) : null}
            <button className="btn fullWidth" onClick={handleUpload} disabled={!sessionId || manualFiles.length === 0 || isUploading}>
              {isUploading ? "Processing manuals…" : "Process manuals"}
            </button>
            {manualsReady ? (
              <div className="notice noticeSuccess">Ready for manual-grounded questions.</div>
            ) : (
              <div className="notice noticeWarn">Process at least one manual before asking.</div>
            )}
            {documents.length > 0 ? (
              <ul className="manualList">
                {documents.map((document) => <li key={document}>{document}</li>)}
              </ul>
            ) : null}
            {uploadWarnings.map((warning) => (
              <div className="notice noticeWarn" key={warning}>{warning}</div>
            ))}
          </div>

          <div className="panel stack">
            <h2>2. Optional inputs</h2>
            <div>
              <h3>Voice note</h3>
              <input className="fileInput" type="file" accept="audio/*" onChange={handleAudioChange} />
              <button className="btn btnGhost fullWidth" style={{ marginTop: 10 }} disabled={!audioFile || isTranscribing} onClick={handleTranscribe}>
                {isTranscribing ? "Transcribing…" : "Transcribe voice note"}
              </button>
            </div>
            <div>
              <h3>Image</h3>
              <input className="fileInput" type="file" accept="image/png,image/jpeg,image/webp" onChange={handleImageChange} />
              {imagePreview ? <img className="imagePreview" src={imagePreview} alt="Selected troubleshooting input" /> : null}
              <p className="helper">Images are used for visible observations only, not diagnosis.</p>
            </div>
          </div>
        </aside>

        <section>
          <div className="panel stack">
            <div className="row spaceBetween">
              <h2>3. Ask the assistant</h2>
              <span className="pill">Manual-grounded RAG</span>
            </div>
            <textarea
              className="textArea"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Example: My bike jerks while accelerating."
            />
            <p className="helper">Tip: include the bike model when several manuals are uploaded, e.g. “For Pulsar NS160…”</p>
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button className="exampleBtn" key={example} onClick={() => setQuery(example)}>
                  {example}
                </button>
              ))}
            </div>
            <button className="btn fullWidth" disabled={askDisabled} onClick={handleAsk}>
              {isAsking ? "Checking manual evidence…" : "Ask from manuals"}
            </button>
          </div>

          {result ? <ResultView result={result} /> : null}
        </section>
      </section>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span className="statLabel">{label}</span>
      <span className="statValue">{value}</span>
    </div>
  );
}

function ResultView({ result }: { result: TroubleshootResponse }) {
  return (
    <div className="panel" style={{ marginTop: 18 }}>
      <h2>Result</h2>
      {result.vision_warning ? <div className="notice noticeWarn">{result.vision_warning}</div> : null}
      {result.vision_observation ? <ObservationView result={result} /> : null}

      <div className="resultGrid">
        <Stat label="Status" value={result.status.replaceAll("_", " ")} />
        <Stat label="Confidence" value={`${result.confidence_level} · ${result.confidence_score.toFixed(2)}`} />
        <Stat label="Citations" value={String(result.citations?.length ?? 0)} />
      </div>

      {result.status === "clarification_needed" ? (
        <div className="notice noticeInfo">
          <strong>I need a bit more detail.</strong>
          <ul>
            {result.clarification_questions.map((question) => <li key={question}>{question}</li>)}
          </ul>
        </div>
      ) : null}

      {result.status === "low_confidence" ? (
        <div className="notice noticeWarn">
          <strong>Not enough manual support.</strong>
          <p>{result.message ?? "I could not find enough support in the uploaded manuals to answer confidently."}</p>
          {result.clarification_questions.length ? (
            <ul>{result.clarification_questions.map((question) => <li key={question}>{question}</li>)}</ul>
          ) : null}
        </div>
      ) : null}

      {result.status === "success" ? (
        <>
          <div className="resultSection">
            <h3>Issue summary</h3>
            <p className="resultText">{result.issue_summary ?? "No supported summary returned."}</p>
            <h3>Possible cause</h3>
            <p className="resultText">{result.possible_cause ?? "No supported cause returned."}</p>
            <h3>Recommended action</h3>
            <p className="resultText">{result.recommended_action ?? "No supported action returned."}</p>
          </div>
          {result.safety_warning ? <div className="notice noticeError">{result.safety_warning}</div> : null}
          {result.escalation_recommendation ? <div className="notice noticeInfo">{result.escalation_recommendation}</div> : null}
          <div className="resultSection">
            <h3>Manual references</h3>
            {result.citations?.length ? result.citations.map((citation, index) => (
              <div className="citation" key={`${citation.document_name}-${citation.page_start}-${index}`}>
                <strong>[{index + 1}] {citation.document_name}</strong>
                <div className="citationMeta">Pages {citation.page_start}-{citation.page_end} · {citation.section_title}</div>
                <blockquote>{citation.excerpt}</blockquote>
              </div>
            )) : <div className="notice noticeWarn">No citation returned. Treat this as unsupported.</div>}
          </div>
        </>
      ) : null}
    </div>
  );
}

function ObservationView({ result }: { result: TroubleshootResponse }) {
  const observation = result.vision_observation;
  if (!observation) return null;
  return (
    <div className="resultSection">
      <h3>Image observations used for retrieval</h3>
      <div className="observationGrid">
        <ObservationBox title="Visible observations" values={observation.visible_observations} />
        <ObservationBox title="Visible text" values={observation.visible_text} />
        <ObservationBox title="Visible components" values={observation.visible_components} />
        <ObservationBox title="Uncertainties" values={observation.uncertainties} />
      </div>
      {result.enriched_query ? (
        <details style={{ marginTop: 12 }}>
          <summary>Retrieval trace: enriched query</summary>
          <pre className="debugBox">{result.enriched_query}</pre>
        </details>
      ) : null}
    </div>
  );
}

function ObservationBox({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="observationBox">
      <h4>{title}</h4>
      {values.length ? (
        <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul>
      ) : <p className="helper">None reported.</p>}
    </div>
  );
}
