import { createContext, useContext } from "react";

import type { ApiRequestError, OptimizeRequest, OptimizeResponse, Recommendation, RefineReference, ValidateResponse } from "../lib/api/client.ts";
import type { EditableDraft } from "../lib/validation/draft.ts";

export type PlannerPhase = "idle" | "editing" | "validating" | "optimizing" | "error";

export type PlannerController = {
  editable: EditableDraft;
  draftEpoch: number;
  mode: "generate" | "refine";
  reference: RefineReference | null;
  publishEditable: (draft: EditableDraft) => void;
  resetForm: () => void;
  leaveRefine: () => void;
  startRefine: (build: Recommendation) => void;
  search: (draft: EditableDraft) => Promise<void>;
  phase: PlannerPhase;
  serverValidation: ValidateResponse | null;
  validationNote: string | null;
  searchError: ApiRequestError | null;
  result: OptimizeResponse | null;
  submittedRequest: OptimizeRequest | null;
  compareIds: string[];
  compareNotice: string | null;
  toggleCompare: (buildId: string) => void;
  removeCompare: (buildId: string) => void;
};

export const PlannerContext = createContext<PlannerController | null>(null);

export function usePlanner(): PlannerController {
  const value = useContext(PlannerContext);
  if (!value) {
    throw new Error("Planner is missing.");
  }
  return value;
}
