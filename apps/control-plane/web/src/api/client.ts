export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

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

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
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
