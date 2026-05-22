import type {
  IngestResponse,
  SessionResponse,
  TranscribeResponse,
  TroubleshootResponse,
} from "@/types/api";

const CONFIGURED_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;
const API_BASE_URL = CONFIGURED_API_BASE_URL ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

export function getApiBaseUrl(): string {
  return API_BASE_URL || "Missing NEXT_PUBLIC_API_BASE_URL";
}

type RequestOptions = RequestInit & {
  timeoutMs?: number;
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

  if (!API_BASE_URL) {
    throw new ApiClientError(
      "Frontend backend URL is not configured. Set NEXT_PUBLIC_API_BASE_URL in Vercel and redeploy.",
      { code: "missing_api_base_url" },
    );
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
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
      throw new ApiClientError("Request failed. Please try again.", { status: response.status });
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiClientError("The request took too long. Please try again.", { code: "timeout" });
    }
    throw new ApiClientError("Could not reach the backend. Please check that it is running.", {
      code: "connection_error",
    });
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
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return requestJson<IngestResponse>(`/sessions/${sessionId}/manuals`, {
    method: "POST",
    body: formData,
    timeoutMs: 240_000,
  });
}

export function transcribeAudio(file: File): Promise<TranscribeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<TranscribeResponse>("/transcribe", {
    method: "POST",
    body: formData,
    timeoutMs: 150_000,
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
  });
}
