import type { operations } from "./schema.ts";

export type MetadataResponse =
  operations["metadata_api_v1_metadata_get"]["responses"][200]["content"]["application/json"];

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
