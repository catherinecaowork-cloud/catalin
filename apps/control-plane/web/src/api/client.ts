export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const TOKEN_STORAGE_KEY = "atp_api_token";

let cachedToken: string | null | undefined;

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "object" && item && "msg" in item) {
          return String((item as { msg?: string }).msg ?? JSON.stringify(item));
        }
        return JSON.stringify(item);
      })
      .join("；");
  }
  if (detail) return JSON.stringify(detail);
  return "";
}

export function getStoredApiToken(): string {
  if (typeof cachedToken === "string") return cachedToken;
  try {
    cachedToken = localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  } catch {
    cachedToken = "";
  }
  return cachedToken;
}

export function setStoredApiToken(token: string): void {
  cachedToken = token;
  try {
    if (token) localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* ignore quota / private mode */
  }
}

/** 本机控制台：从 /auth/bootstrap 取 token；远程需手工配置。 */
export async function ensureApiToken(): Promise<string> {
  const existing = getStoredApiToken();
  if (existing) return existing;
  try {
    const response = await fetch("/api/v1/auth/bootstrap");
    if (!response.ok) return "";
    const body = (await response.json()) as {
      api_token?: string;
      loopback?: boolean;
    };
    if (body.api_token) {
      setStoredApiToken(body.api_token);
      return body.api_token;
    }
  } catch {
    /* ignore */
  }
  return "";
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  await ensureApiToken();
  const token = getStoredApiToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["X-API-Token"] = token;

  const response = await fetch(path, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = formatDetail((body as { detail?: unknown }).detail);
    throw new ApiError(
      response.status,
      detail || `${response.status} ${response.statusText}`,
    );
  }
  if (response.status === 204) return {} as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : {}) as T;
}
