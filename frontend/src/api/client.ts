const DEFAULT_API_BASE_URL = "http://127.0.0.1:5000/api/v1";

type ApiEnvelope<T> = {
  data?: T;
  meta?: Record<string, unknown>;
  error?: {
    code?: string;
    message?: string;
  };
};

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined
>;

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "request_failed") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function getApiBaseUrl() {
  return (
    import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || DEFAULT_API_BASE_URL
  );
}

export function buildQuery(params: QueryParams = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers,
  });
  const payload = (await response.json().catch(() => ({}))) as ApiEnvelope<T>;

  if (!response.ok) {
    throw new ApiError(
      payload.error?.message || `Request failed with status ${response.status}`,
      response.status,
      payload.error?.code
    );
  }

  return payload.data as T;
}

export function jsonBody(value: unknown) {
  return JSON.stringify(value);
}
