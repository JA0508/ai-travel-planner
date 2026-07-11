"use client";

export type TripApiResult<TData> =
  | {
      ok: true;
      data: TData;
    }
  | {
      ok: false;
      message: string;
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
    return {
      ok: false,
      message: extractApiDetail(data) ?? fallbackMessage,
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
