import type { components, operations } from "./schema.ts";

export type MetadataResponse =
  operations["metadata_api_v1_metadata_get"]["responses"][200]["content"]["application/json"];

export type OptimizeRequest = components["schemas"]["OptimizeRequest"];
export type ValidateResponse = components["schemas"]["ValidateResponse"];
export type OptimizeResponse =
  operations["optimize_build_api_v1_optimize_post"]["responses"][200]["content"]["application/json"];
export type Recommendation = components["schemas"]["Recommendation"];
export type RefineReference = components["schemas"]["RefineReference"];
export type ApiErrorBody = components["schemas"]["ErrorResponse"];

export type ApiErrorDetail = {
  field: string;
  message: string;
};

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly details: ApiErrorDetail[];

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string,
    details: ApiErrorDetail[],
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

function apiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (!configured) {
    return "";
  }
  return configured.replace(/\/$/, "");
}

export async function getMetadata(): Promise<MetadataResponse> {
  const response = await fetch(`${apiBase()}/api/v1/metadata`);
  if (!response.ok) {
    throw new Error(`Metadata request failed (${response.status})`);
  }
  return (await response.json()) as MetadataResponse;
}

export async function validateBuild(
  body: OptimizeRequest,
  signal?: AbortSignal,
): Promise<ValidateResponse> {
  return postJson<ValidateResponse>("/api/v1/validate", body, signal);
}

export async function optimizeBuild(body: OptimizeRequest): Promise<OptimizeResponse> {
  return postJson<OptimizeResponse>("/api/v1/optimize", body);
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiRequestError(
      0,
      "network",
      "The planning service could not be reached. Start the API and try again.",
      "",
      [],
    );
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as T;
}

async function errorFromResponse(response: Response): Promise<ApiRequestError> {
  const payload = (await response.json().catch(() => null)) as ApiErrorBody | null;
  const message = payload?.message || fallbackMessage(response.status);
  return new ApiRequestError(
    response.status,
    payload?.code ?? "request_failed",
    message,
    payload?.request_id ?? "",
    (payload?.details ?? []).map((detail) => ({
      field: detail.field,
      message: detail.message,
    })),
  );
}

function fallbackMessage(status: number): string {
  if (status === 429) {
    return "Too many requests. Wait a moment and try again.";
  }
  if (status === 503) {
    return "The planning service is unavailable. Retry, and keep the request id if it continues.";
  }
  if (status === 422) {
    return "The request is not a valid build query.";
  }
  return "The planning service hit an unexpected error. Retry once.";
}
