import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiRequestError,
  getMetadata,
  optimizeBuild,
  validateBuild,
  type OptimizeRequest,
  type OptimizeResponse,
  type Recommendation,
  type RefineReference,
  type ValidateResponse,
} from "../lib/api/client.ts";
import {
  catalogFrom,
  coerceEditable,
  emptyEditable,
  inspectDraft,
  type EditableDraft,
} from "../lib/validation/draft.ts";
import { PlannerContext, type PlannerPhase } from "./planner.ts";

const VALIDATE_DELAY_MS = 400;

export function PlannerProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const metadata = useQuery({ queryKey: ["metadata"], queryFn: getMetadata });
  const catalog = useMemo(
    () => (metadata.data ? catalogFrom(metadata.data) : null),
    [metadata.data],
  );
  const [editable, setEditable] = useState<EditableDraft>(emptyEditable);
  const [draftEpoch, setDraftEpoch] = useState(0);
  const [mode, setMode] = useState<"generate" | "refine">("generate");
  const [reference, setReference] = useState<RefineReference | null>(null);
  const [phase, setPhase] = useState<PlannerPhase>("idle");
  const [serverValidation, setServerValidation] = useState<ValidateResponse | null>(null);
  const [validationNote, setValidationNote] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<ApiRequestError | null>(null);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [submittedRequest, setSubmittedRequest] = useState<OptimizeRequest | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareNotice, setCompareNotice] = useState<string | null>(null);
  const published = useRef(JSON.stringify(emptyEditable()));

  const publishEditable = useCallback((draft: EditableDraft) => {
    const next = coerceEditable(draft);
    const serial = JSON.stringify(next);
    if (serial === published.current) {
      return;
    }
    published.current = serial;
    setEditable(next);
    setPhase((current) => (current === "optimizing" ? current : "editing"));
  }, []);

  useEffect(() => {
    if (!catalog) {
      return;
    }
    const inspected = inspectDraft(editable, mode, reference, catalog);
    if (inspected.request === null) {
      setServerValidation((current) => (current === null ? current : null));
      setPhase((current) => (current === "validating" ? "editing" : current));
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setPhase((current) => (current === "optimizing" ? current : "validating"));
      validateBuild(inspected.request as OptimizeRequest, controller.signal)
        .then((response) => {
          if (controller.signal.aborted) {
            return;
          }
          setServerValidation(response);
          setValidationNote(null);
          setPhase((current) => (current === "optimizing" ? current : "editing"));
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
            return;
          }
          const message =
            error instanceof ApiRequestError
              ? error.message
              : "The rules check could not be completed.";
          setValidationNote(`${message} Generate will still send the search.`);
          setPhase((current) => (current === "optimizing" ? current : "editing"));
        });
    }, VALIDATE_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [catalog, editable, mode, reference]);

  const replaceEditable = useCallback((next: EditableDraft) => {
    published.current = JSON.stringify(next);
    setEditable(next);
    setDraftEpoch((epoch) => epoch + 1);
  }, []);

  const resetForm = useCallback(() => {
    setMode("generate");
    setReference(null);
    setSearchError(null);
    setServerValidation(null);
    setValidationNote(null);
    setPhase("idle");
    replaceEditable(emptyEditable());
  }, [replaceEditable]);

  const leaveRefine = useCallback(() => {
    setMode("generate");
    setReference(null);
    setEditable((current) => {
      const next = {
        ...current,
        buildTypeLocked: false,
        positionLocked: false,
        heightLocked: false,
        weightLocked: false,
        wingspanLocked: false,
      };
      published.current = JSON.stringify(next);
      return next;
    });
    setDraftEpoch((epoch) => epoch + 1);
  }, []);

  const startRefine = useCallback(
    (build: Recommendation) => {
      setMode("refine");
      setReference({
        body: build.body,
        base_attributes: build.base_attributes,
        cap_breaker_allocations: build.cap_breaker_allocations,
      });
      setEditable((current) => {
        const next = {
          ...current,
          buildType: build.body.build_type,
          buildTypeLocked: true,
          position: build.body.position,
          positionLocked: true,
          height: String(build.body.height_in),
          heightLocked: true,
          weight: String(build.body.weight_lb),
          weightLocked: true,
          wingspan: String(build.body.wingspan_in),
          wingspanLocked: true,
        };
        published.current = JSON.stringify(next);
        return next;
      });
      setDraftEpoch((epoch) => epoch + 1);
      navigate("/build");
    },
    [navigate],
  );

  const search = useCallback(
    async (draft: EditableDraft) => {
      if (!catalog) {
        return;
      }
      const inspected = inspectDraft(draft, mode, reference, catalog);
      if (inspected.request === null) {
        return;
      }
      setPhase("optimizing");
      setSearchError(null);
      try {
        const response = await optimizeBuild(inspected.request);
        setResult(response);
        setSubmittedRequest(inspected.request);
        setCompareIds([]);
        setCompareNotice(null);
        setPhase("idle");
        navigate("/results");
      } catch (error) {
        const failure =
          error instanceof ApiRequestError
            ? error
            : new ApiRequestError(0, "network", "The planning service could not be reached.", "", []);
        setSearchError(failure);
        setPhase("error");
      }
    },
    [catalog, mode, navigate, reference],
  );

  const toggleCompare = useCallback((buildId: string) => {
    setCompareIds((current) => {
      if (current.includes(buildId)) {
        setCompareNotice(null);
        return current.filter((id) => id !== buildId);
      }
      if (current.length >= 3) {
        setCompareNotice("Three builds are already selected. Remove one to add another.");
        return current;
      }
      setCompareNotice(null);
      return [...current, buildId];
    });
  }, []);

  const removeCompare = useCallback((buildId: string) => {
    setCompareNotice(null);
    setCompareIds((current) => current.filter((id) => id !== buildId));
  }, []);

  const value = useMemo(
    () => ({
      editable,
      draftEpoch,
      mode,
      reference,
      publishEditable,
      resetForm,
      leaveRefine,
      startRefine,
      search,
      phase,
      serverValidation,
      validationNote,
      searchError,
      result,
      submittedRequest,
      compareIds,
      compareNotice,
      toggleCompare,
      removeCompare,
    }),
    [
      editable,
      draftEpoch,
      mode,
      reference,
      publishEditable,
      resetForm,
      leaveRefine,
      startRefine,
      search,
      phase,
      serverValidation,
      validationNote,
      searchError,
      result,
      submittedRequest,
      compareIds,
      compareNotice,
      toggleCompare,
      removeCompare,
    ],
  );

  return <PlannerContext.Provider value={value}>{children}</PlannerContext.Provider>;
}
