const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export function apiUrl(path: string): string {
  return `${apiBaseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiResponse(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(apiUrl(path), init);

  if (response.ok) return response;

  const body: unknown = await response.json().catch(() => null);

  if (body && typeof body === "object") {
    if ("error" in body && body.error && typeof body.error === "object") {
      const error = body.error;

      if ("message" in error && typeof error.message === "string") {
        throw new ApiError(
          error.message,
          response.status,
          "code" in error && typeof error.code === "string" ? error.code : undefined,
        );
      }
    }

    if ("detail" in body) {
      if (typeof body.detail === "string") throw new ApiError(body.detail, response.status);

      if (Array.isArray(body.detail)) {
        const messages = body.detail.flatMap((detail: unknown) => {
          if (
            !detail ||
            typeof detail !== "object" ||
            !("msg" in detail) ||
            typeof detail.msg !== "string"
          )
            return [];

          const field =
            "loc" in detail && Array.isArray(detail.loc)
              ? detail.loc.filter((part: unknown) => part !== "body").join(".")
              : "";

          return [field ? `${field}: ${detail.msg}` : detail.msg];
        });

        if (messages.length) throw new ApiError(messages.join("; "), response.status);
      }
    }
  }

  throw new ApiError(`API request failed with status ${response.status}`, response.status);
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;

  if (init?.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await apiResponse(path, {
    ...init,
    headers,
  });

  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return (await response.json()) as T;
}
