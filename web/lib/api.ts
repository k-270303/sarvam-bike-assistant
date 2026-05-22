import type {
  ChunkedUploadPartialResponse,
  ChunkedUploadStartResponse,
  IngestResponse,
  SessionResponse,
  TranscribeResponse,
  TroubleshootResponse,
} from "@/types/api";

const CONFIGURED_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;
const API_BASE_URL = CONFIGURED_API_BASE_URL ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "/backend");
const UPLOAD_API_BASE_URL = process.env.NEXT_PUBLIC_UPLOAD_API_BASE_URL
  ?? (process.env.NODE_ENV === "development" ? API_BASE_URL : "https://sarvam-bike-assistant-api.onrender.com");
const CHUNKED_UPLOAD_THRESHOLD_BYTES = 6 * 1024 * 1024;
const DEFAULT_UPLOAD_CHUNK_BYTES = 3 * 1024 * 1024;

export function getApiBaseUrl(): string {
  return API_BASE_URL || "Missing NEXT_PUBLIC_API_BASE_URL";
}

export function getUploadApiBaseUrl(): string {
  return UPLOAD_API_BASE_URL;
}

type RequestOptions = RequestInit & {
  timeoutMs?: number;
  baseUrl?: string;
};

export class ApiClientError extends Error {
  code?: string;
  status?: number;

  constructor(message: string, options?: { code?: string; status?: number }) {
    super(message);
    this.name = "ApiClientError";
    this.code = options?.code;
    this.status = options?.status;
  }
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs ?? 120_000);
  const { baseUrl = API_BASE_URL, timeoutMs: _timeoutMs, ...fetchOptions } = options;

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...fetchOptions,
      signal: controller.signal,
    });

    let payload: unknown = null;
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      payload = await response.json();
    }

    if (!response.ok) {
      const detail = typeof payload === "object" && payload !== null && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : undefined;
      if (typeof detail === "object" && detail !== null) {
        const error = detail as { message?: string; code?: string };
        throw new ApiClientError(error.message ?? "Request failed.", {
          code: error.code,
          status: response.status,
        });
      }
      if (typeof detail === "string") {
        throw new ApiClientError(detail, { status: response.status });
      }
      const fallbackBody = typeof payload === "string" ? payload.slice(0, 300) : "";
      throw new ApiClientError(
        `Request failed (${response.status} ${response.statusText}) at ${baseUrl}${path}.${fallbackBody ? ` Response: ${fallbackBody}` : ""}`,
        { status: response.status },
      );
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiClientError("The request took too long. Please try again.", { code: "timeout" });
    }
    const reason = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    throw new ApiClientError(
      `Could not reach the backend at ${baseUrl}${path}. Browser error: ${reason}`,
      { code: "connection_error" },
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

export function createSession(): Promise<SessionResponse> {
  return requestJson<SessionResponse>("/sessions", {
    method: "POST",
    timeoutMs: 30_000,
  });
}

export function uploadManuals(sessionId: string, files: File[]): Promise<IngestResponse> {
  if (files.every((file) => file.size <= CHUNKED_UPLOAD_THRESHOLD_BYTES)) {
    return uploadManualBatch(sessionId, files);
  }

  return uploadManualsSafely(sessionId, files);
}

function uploadManualBatch(sessionId: string, files: File[]): Promise<IngestResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return requestJson<IngestResponse>(`/sessions/${sessionId}/manuals`, {
    method: "POST",
    body: formData,
    timeoutMs: 240_000,
    baseUrl: UPLOAD_API_BASE_URL,
  });
}

async function uploadManualsSafely(sessionId: string, files: File[]): Promise<IngestResponse> {
  let latestResponse: IngestResponse | null = null;

  for (const file of files) {
    if (file.size <= CHUNKED_UPLOAD_THRESHOLD_BYTES) {
      latestResponse = await uploadManualBatch(sessionId, [file]);
      continue;
    }

    latestResponse = await uploadLargeManualInChunks(sessionId, file);
  }

  if (!latestResponse) {
    throw new ApiClientError("Please upload at least one PDF manual.", { code: "no_files" });
  }
  return latestResponse;
}

async function uploadLargeManualInChunks(sessionId: string, file: File): Promise<IngestResponse> {
  const optimisticChunkSize = DEFAULT_UPLOAD_CHUNK_BYTES;
  const start = await requestJson<ChunkedUploadStartResponse>(`/sessions/${sessionId}/manual-upload/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      total_chunks: Math.ceil(file.size / optimisticChunkSize),
      total_size: file.size,
    }),
    timeoutMs: 30_000,
    baseUrl: UPLOAD_API_BASE_URL,
  });

  const chunkSize = Math.min(start.chunk_size_hint || optimisticChunkSize, optimisticChunkSize);
  const totalChunks = Math.ceil(file.size / chunkSize);

  if (totalChunks !== Math.ceil(file.size / optimisticChunkSize)) {
    throw new ApiClientError(
      "The upload chunk size changed unexpectedly. Please refresh and retry.",
      { code: "chunk_config_mismatch" },
    );
  }

  for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
    const startByte = chunkIndex * chunkSize;
    const endByte = Math.min(startByte + chunkSize, file.size);
    const formData = new FormData();
    formData.append("chunk_index", String(chunkIndex));
    formData.append("chunk", file.slice(startByte, endByte), `${file.name}.part-${chunkIndex}`);

    const response = await requestJson<IngestResponse | ChunkedUploadPartialResponse>(
      `/sessions/${sessionId}/manual-upload/${start.upload_id}/chunk`,
      {
        method: "POST",
        body: formData,
        timeoutMs: 240_000,
        baseUrl: UPLOAD_API_BASE_URL,
      },
    );

    if ("chunks_indexed" in response) {
      return response;
    }
  }

  throw new ApiClientError("The upload finished without an indexing response. Please retry.", {
    code: "chunk_upload_incomplete",
  });
}

export function transcribeAudio(file: File): Promise<TranscribeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<TranscribeResponse>("/transcribe", {
    method: "POST",
    body: formData,
    timeoutMs: 150_000,
    baseUrl: UPLOAD_API_BASE_URL,
  });
}

export function troubleshoot(sessionId: string, query: string): Promise<TroubleshootResponse> {
  return requestJson<TroubleshootResponse>("/troubleshoot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, query }),
    timeoutMs: 150_000,
  });
}

export function troubleshootWithImage(
  sessionId: string,
  query: string,
  image: File,
): Promise<TroubleshootResponse> {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("query", query);
  formData.append("image", image);
  return requestJson<TroubleshootResponse>("/troubleshoot/image", {
    method: "POST",
    body: formData,
    timeoutMs: 210_000,
    baseUrl: UPLOAD_API_BASE_URL,
  });
}

export async function checkBackendConnection(): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/health", {
    method: "GET",
    timeoutMs: 30_000,
  });
}
