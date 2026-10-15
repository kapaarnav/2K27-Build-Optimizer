import type { FieldErrors, UseFormReturn } from "react-hook-form";

import type { EditableDraft } from "../../lib/validation/draft.ts";

export function fieldMessage(errors: FieldErrors<EditableDraft>, path: string): string | undefined {
  const parts = path.split(".");
  let current: unknown = errors;
  for (const part of parts) {
    if (!current || typeof current !== "object") {
      return undefined;
    }
    current = (current as Record<string, unknown>)[part];
  }
  if (!current || typeof current !== "object") {
    return undefined;
  }
  if ("message" in current && typeof current.message === "string" && current.message) {
    return current.message;
  }
  if ("root" in current && current.root && typeof current.root === "object" && "message" in current.root) {
    const message = current.root.message;
    return typeof message === "string" ? message : undefined;
  }
  return undefined;
}

export function FieldMessage({ id, message }: { id: string; message?: string }) {
  if (!message) {
    return null;
  }
  return (
    <p id={id} className="mt-1 text-sm text-stone-700">
      {message}
    </p>
  );
}

export function describedBy(id: string, message?: string, hintId?: string): string | undefined {
  const ids = [hintId, message ? id : undefined].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}

export type BuilderControl = UseFormReturn<EditableDraft>;
