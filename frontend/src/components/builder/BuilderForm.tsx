import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useRef } from "react";
import { useForm, type FieldErrors } from "react-hook-form";

import { choiceLabel, formatInches, formatWeight } from "../../lib/format.ts";
import type { MetadataResponse } from "../../lib/api/client.ts";
import { attributeLabel } from "../../lib/validation/draft.ts";
import {
  catalogFrom,
  coerceEditable,
  createDraftSchema,
  type EditableDraft,
} from "../../lib/validation/draft.ts";
import { usePlanner } from "../../state/planner.ts";
import { buttonClass, inputClass, labelClass, panelClass, primaryButtonClass } from "../styles.ts";
import { AdvancedOptions } from "./AdvancedOptions.tsx";
import { AttributeBoard } from "./AttributeBoard.tsx";
import { PhysicalFields } from "./PhysicalFields.tsx";

export function BuilderForm({ metadata }: { metadata: MetadataResponse }) {
  const planner = usePlanner();
  const catalog = useMemo(() => catalogFrom(metadata), [metadata]);
  const schema = useMemo(() => createDraftSchema(catalog), [catalog]);
  const form = useForm<EditableDraft>({
    defaultValues: planner.editable,
    resolver: zodResolver(schema),
    mode: "onChange",
    criteriaMode: "all",
  });
  const editableRef = useRef(planner.editable);
  editableRef.current = planner.editable;

  useEffect(() => {
    form.reset(editableRef.current);
    void form.trigger();
  }, [form, planner.draftEpoch]);

  const publishEditable = planner.publishEditable;
  useEffect(() => {
    const subscription = form.watch((value) => {
      publishEditable(coerceEditable(value));
    });
    return () => subscription.unsubscribe();
  }, [form, publishEditable]);

  const messages = uniqueMessages(form.formState.errors);
  const searching = planner.phase === "optimizing";

  return (
    <form
      className="space-y-6"
      noValidate
      aria-busy={searching}
      onSubmit={form.handleSubmit((values) => {
        void planner.search(coerceEditable(values));
      })}
    >
      {metadata.recommendations_enabled ? null : (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          Recommendations are off for ruleset {metadata.ruleset_id}. A search can still
          be sent, and the result names any missing rules.
        </p>
      )}
      {planner.mode === "refine" && planner.reference ? (
        <section aria-labelledby="refine-heading" className={panelClass}>
          <h2 id="refine-heading" className="text-xl font-semibold">
            Refine
          </h2>
          <p className="mt-2 text-sm text-stone-700">
            The body is locked to the selected build. Reference ratings stay in place
            as a starting point. Add a target when you want a rating to become an
            explicit request.
          </p>
          <h3 className="mt-4 text-sm font-semibold text-stone-800">Reference ratings</h3>
          <ul className="mt-2 grid gap-1 text-sm text-stone-800 sm:grid-cols-2">
            {planner.reference.base_attributes.map((item) => (
              <li key={item.id}>
                {attributeLabel(catalog, item.id)}: {item.rating}
              </li>
            ))}
          </ul>
          <h3 className="mt-4 text-sm font-semibold text-stone-800">Reference Cap Breakers</h3>
          {(planner.reference.cap_breaker_allocations ?? []).length === 0 ? (
            <p className="mt-1 text-sm text-stone-700">This build has no Cap Breaker allocations.</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm text-stone-800">
              {planner.reference.cap_breaker_allocations?.map((item) => (
                <li key={`${item.pool_id}-${item.attribute_id}`}>
                  {item.pool_id} on {attributeLabel(catalog, item.attribute_id)}: {item.applications}{" "}
                  applications, {item.rating_gain} rating gain
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-sm text-stone-700">
            {planner.reference.body.position} · {choiceLabel(planner.reference.body.build_type)} ·{" "}
            {formatInches(planner.reference.body.height_in)} · {formatWeight(planner.reference.body.weight_lb)} ·{" "}
            wingspan {formatInches(planner.reference.body.wingspan_in)}
          </p>
          <button type="button" className={`${buttonClass} mt-4`} onClick={planner.leaveRefine}>
            Leave refine
          </button>
        </section>
      ) : null}
      <PhysicalFields form={form} catalog={catalog} />
      <AttributeBoard form={form} catalog={catalog} />
      <section aria-labelledby="playstyle-heading" className={panelClass}>
        <h2 id="playstyle-heading" className="text-xl font-semibold">
          Playstyle
        </h2>
        <label className={`${labelClass} mt-4`} htmlFor="playstyle">
          Scoring emphasis
        </label>
        <select id="playstyle" className={inputClass} {...form.register("playstyle")}>
          {metadata.playstyles.map((playstyle) => (
            <option key={playstyle.id} value={playstyle.id}>
              {playstyle.label}
            </option>
          ))}
        </select>
        <p className="mt-2 text-sm text-stone-600">
          Playstyle changes how unspecified strengths are scored. It does not change game rules.
        </p>
      </section>
      <AdvancedOptions form={form} catalog={catalog} />
      <div aria-live="polite" className="space-y-3">
        {messages.length > 0 ? (
          <ul className="list-disc pl-5 text-sm text-stone-800">
            {messages.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}
        {planner.phase === "validating" ? (
          <p role="status" className="text-sm text-stone-700">
            Checking this request against verified rules.
          </p>
        ) : null}
        {planner.validationNote ? (
          <p role="status" className="text-sm text-stone-700">
            {planner.validationNote}
          </p>
        ) : null}
        {planner.serverValidation ? <RulesCheck validation={planner.serverValidation} /> : null}
        {planner.searchError ? (
          <p role="alert" className="rounded-lg border border-stone-300 bg-stone-100 px-4 py-3 text-sm text-stone-900">
            {planner.searchError.message}
            {planner.searchError.requestId ? ` Request ${planner.searchError.requestId}.` : ""}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-3">
        <button type="submit" className={primaryButtonClass} disabled={!form.formState.isValid || searching}>
          {searching ? "Searching…" : "Generate builds"}
        </button>
        <button type="button" className={buttonClass} onClick={planner.resetForm}>
          Reset form
        </button>
      </div>
    </form>
  );
}

function RulesCheck({
  validation,
}: {
  validation: NonNullable<ReturnType<typeof usePlanner>["serverValidation"]>;
}) {
  const coverageIssue = validation.issues.find((issue) => issue.code === "coverage_unsupported");
  const otherIssues = validation.issues.filter((issue) => issue.code !== "coverage_unsupported");
  const tone = validation.supported
    ? "border-stone-200 bg-white"
    : "border-amber-200 bg-amber-50";
  return (
    <section aria-labelledby="rules-check-heading" className={`rounded-lg border px-4 py-3 ${tone}`}>
      <h2 id="rules-check-heading" className="text-sm font-semibold">
        Rules check
      </h2>
      {coverageIssue ? <p className="mt-1 text-sm text-stone-800">{coverageIssue.message}</p> : null}
      {validation.supported ? (
        <p className="mt-1 text-sm text-stone-800">Verified rules cover this request.</p>
      ) : null}
      {otherIssues.length > 0 ? (
        <ul className="mt-2 list-disc pl-5 text-sm text-stone-800">
          {otherIssues.map((issue) => (
            <li key={`${issue.field}-${issue.message}`}>{issue.message}</li>
          ))}
        </ul>
      ) : null}
      {validation.warnings.length > 0 ? (
        <ul className="mt-2 list-disc pl-5 text-sm text-stone-700">
          {validation.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function uniqueMessages(errors: FieldErrors<EditableDraft>): string[] {
  return [...new Set(collectMessages(errors))];
}

function collectMessages(value: unknown): string[] {
  if (!value || typeof value !== "object") {
    return [];
  }
  const record = value as Record<string, unknown>;
  const messages: string[] = [];
  if (typeof record.message === "string" && record.message) {
    messages.push(record.message);
  }
  for (const [key, child] of Object.entries(record)) {
    if (key === "message" || key === "type" || key === "ref") {
      continue;
    }
    messages.push(...collectMessages(child));
  }
  return messages;
}
