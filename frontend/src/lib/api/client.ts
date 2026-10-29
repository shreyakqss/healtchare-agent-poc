/** Browser requests stay same-origin; the fixed BFF route owns the backend boundary. */

export const API_ROOT = "/api/careflow";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, detail || `Request failed (${res.status})`);
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const method = (init.method ?? "GET").toUpperCase();
  const csrf = method === "GET" || method === "HEAD" ? null : readCookie("careflow_csrf");
  const res = await fetch(`${API_ROOT}${path}`, {
    cache: "no-store",
    credentials: "same-origin",
    ...init,
    headers: {
      ...(isForm || init.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(csrf ? { "x-csrf-token": csrf } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  const value = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  form: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};

/** Parse a `text/event-stream` response body frame by frame. */
export async function* readSse<T>(res: Response): AsyncGenerator<T> {
  if (!res.ok || !res.body) throw await parseError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, "\n");
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const data = sseData(frame);
      if (data) yield JSON.parse(data) as T;
    }
  }
  buffer += decoder.decode();
  const finalData = sseData(buffer.replace(/\r\n/g, "\n").trim());
  if (finalData) yield JSON.parse(finalData) as T;
}

function sseData(frame: string): string {
  return frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
}

/** The doctor workspace loads every clinic case in one call (the API allows up to 1000), so an
 * older booking is never missing from the worklist or calendar. */
export const WORKSPACE_CASES = 1000;
