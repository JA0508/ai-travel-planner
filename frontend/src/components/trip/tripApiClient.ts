"use client";

export type TripApiResult<TData> =
  | {
      ok: true;
      data: TData;
    }
  | {
      ok: false;
      message: string;
      code?: string;
      responseStatus?: number;
      recoverable?: boolean;
      context?: Record<string, unknown>;
      aborted?: boolean;
    };

export async function postTripJson<TData>(
  url: string,
  payload: unknown,
  fallbackMessage: string,
  networkMessage = "无法连接后端接口。",
  options: { headers?: Record<string, string>; signal?: AbortSignal } = {},
): Promise<TripApiResult<TData>> {
  let response: Response;
  const headers = {
    "Content-Type": "application/json",
    "X-Request-ID": options.headers?.["X-Request-ID"] ?? buildClientRequestId(),
    ...options.headers,
  };
  try {
    response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: options.signal,
      credentials: "include",
    });
  } catch (error) {
    if (isAbortError(error)) {
      return {
        ok: false,
        message: "Request aborted.",
        aborted: true,
      };
    }
    return {
      ok: false,
      message: networkMessage,
    };
  }

  const data = await readJsonSafely(response);
  if (!response.ok) {
    const tripError = extractTripError(data);
    return {
      ok: false,
      message: extractApiDetail(data) ?? tripError?.message ?? fallbackMessage,
      code: tripError?.code,
      responseStatus: response.status,
      recoverable: tripError?.recoverable,
      context: tripError?.context,
    };
  }

  return {
    ok: true,
    data: data as TData,
  };
}

export async function getTripJson<TData>(
  url: string,
  fallbackMessage: string,
  networkMessage = "无法连接后端接口。",
  options: { signal?: AbortSignal } = {},
): Promise<TripApiResult<TData>> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      signal: options.signal,
      credentials: "include",
      headers: {
        "X-Request-ID": buildClientRequestId(),
      },
    });
  } catch (error) {
    if (isAbortError(error)) {
      return {
        ok: false,
        message: "Request aborted.",
        aborted: true,
      };
    }
    return {
      ok: false,
      message: networkMessage,
    };
  }

  const data = await readJsonSafely(response);
  if (!response.ok) {
    const tripError = extractTripError(data);
    return {
      ok: false,
      message: extractApiDetail(data) ?? tripError?.message ?? fallbackMessage,
      code: tripError?.code,
      recoverable: tripError?.recoverable,
      context: tripError?.context,
    };
  }

  return {
    ok: true,
    data: data as TData,
  };
}

function extractApiDetail(data: unknown): string | null {
  if (typeof data !== "object" || data === null || !("detail" in data)) {
    return null;
  }
  return formatApiDetail((data as { detail?: unknown }).detail);
}

function extractTripError(data: unknown): {
  code?: string;
  message: string;
  recoverable?: boolean;
  context?: Record<string, unknown>;
} | null {
  if (typeof data !== "object" || data === null || !("error" in data)) {
    return null;
  }
  const error = (data as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) {
    return null;
  }
  const code = "code" in error ? String((error as { code?: unknown }).code ?? "") : "";
  const message = "message" in error
    ? String((error as { message?: unknown }).message ?? "")
    : "";
  const recoverable = "recoverable" in error
    ? Boolean((error as { recoverable?: unknown }).recoverable)
    : undefined;
  const context = Object.fromEntries(
    Object.entries(error).filter(
      ([key]) => !["code", "message", "recoverable"].includes(key),
    ),
  );
  const formatted = [code, message].filter(Boolean).join(": ");
  return formatted
    ? { code: code || undefined, message: formatted, recoverable, context }
    : null;
}

async function readJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function buildClientRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `web-${crypto.randomUUID()}`;
  }
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail.trim() || null;
  }
  if (detail == null) {
    return null;
  }
  if (Array.isArray(detail)) {
    const formattedItems = detail
      .map(formatApiDetail)
      .filter((item): item is string => Boolean(item));
    return formattedItems.length > 0 ? formattedItems.join("；") : null;
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return null;
    }
  }
  return String(detail);
}
