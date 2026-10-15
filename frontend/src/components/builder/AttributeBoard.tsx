import { useMemo, useState } from "react";
import { useFieldArray } from "react-hook-form";

import { choiceLabel } from "../../lib/format.ts";
import {
  attributeLabel,
  RATING_MAX,
  RATING_MIN,
  type Catalog,
} from "../../lib/validation/draft.ts";
import { buttonClass, inputClass, labelClass, panelClass } from "../styles.ts";
import { fieldMessage, FieldMessage, type BuilderControl } from "./form.tsx";

export function AttributeBoard({ form, catalog }: { form: BuilderControl; catalog: Catalog }) {
  const { control, register, watch, formState } = form;
  const targets = useFieldArray({ control, name: "targets", keyName: "fieldKey" });
  const liveTargets = watch("targets");
  const listError = fieldMessage(formState.errors, "targets");
  const [query, setQuery] = useState("");
  const defaultImportance = catalog.importanceLevels.includes("normal")
    ? "normal"
    : (catalog.importanceLevels[0] ?? "normal");

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = catalog.attributes.filter((attribute) => {
      if (!needle) {
        return true;
      }
      return (
        attribute.label.toLowerCase().includes(needle) ||
        attribute.id.toLowerCase().includes(needle) ||
        attribute.category.toLowerCase().includes(needle)
      );
    });
    const grouped = new Map<string, Catalog["attributes"]>();
    for (const attribute of filtered) {
      const rows = grouped.get(attribute.category) ?? [];
      rows.push(attribute);
      grouped.set(attribute.category, rows);
    }
    return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [catalog.attributes, query]);

  return (
    <section aria-labelledby="attributes-heading" className={panelClass}>
      <h2 id="attributes-heading" className="text-xl font-semibold">
        Attribute targets
      </h2>
      <p className="mt-2 text-sm text-stone-700">
        Add the ratings you care about. Anything left as — stays unspecified, and the
        search may choose a legal value. At least one target is required.
      </p>
      {catalog.attributes.length === 0 ? (
        <p className="mt-4 text-sm text-stone-800">
          No verified attributes are in this ruleset. Targets stay unavailable until a
          sourced catalog is loaded.
        </p>
      ) : (
        <>
          <div className="mt-4">
            <label className={labelClass} htmlFor="attribute-search">
              Search attributes
            </label>
            <input
              id="attribute-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className={inputClass}
              autoComplete="off"
            />
          </div>
          <div className="mt-4 space-y-4">
            {groups.length === 0 ? (
              <p className="text-sm text-stone-700">No attributes match that search.</p>
            ) : (
              groups.map(([category, attributes]) => (
                <div key={category}>
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-stone-600">
                    {category}
                  </h3>
                  <ul className="mt-2 divide-y divide-stone-200 border-y border-stone-200">
                    {attributes.map((attribute) => {
                      const index = targets.fields.findIndex((field) => field.id === attribute.id);
                      const live = index === -1 ? undefined : liveTargets[index];
                      return (
                        <li key={attribute.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                          <p>
                            <span className="font-medium">{attribute.label}</span>{" "}
                            {index === -1 ? (
                              <>
                                <span aria-hidden="true">—</span>
                                <span className="sr-only">unspecified</span>
                              </>
                            ) : (
                              <span>
                                {live?.target ? `target ${live.target}` : "selected, needs a rating"}
                              </span>
                            )}
                          </p>
                          {index === -1 ? (
                            <button
                              type="button"
                              className={buttonClass}
                              onClick={() =>
                                targets.append({
                                  id: attribute.id,
                                  target: "",
                                  importance: defaultImportance,
                                })
                              }
                            >
                              Add {attribute.label}
                            </button>
                          ) : (
                            <span className="text-sm text-stone-600">In selected targets</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))
            )}
          </div>
        </>
      )}
      <div className="mt-4">
        <h3 className="text-sm font-semibold text-stone-800">Selected targets</h3>
        {targets.fields.length === 0 ? (
          <p className="mt-1 text-sm text-stone-700">No targets selected.</p>
        ) : (
          <ul className="mt-3 space-y-4">
            {targets.fields.map((field, index) => (
              <li key={field.fieldKey}>
                <TargetRow
                  form={form}
                  index={index}
                  label={attributeLabel(catalog, field.id)}
                  importanceLevels={catalog.importanceLevels}
                  onRemove={() => targets.remove(index)}
                  registration={register}
                />
              </li>
            ))}
          </ul>
        )}
        {listError ? <p className="mt-2 text-sm text-stone-800">{listError}</p> : null}
      </div>
    </section>
  );
}

function TargetRow({
  form,
  index,
  label,
  importanceLevels,
  onRemove,
  registration,
}: {
  form: BuilderControl;
  index: number;
  label: string;
  importanceLevels: readonly string[];
  onRemove: () => void;
  registration: BuilderControl["register"];
}) {
  const message = fieldMessage(form.formState.errors, `targets.${index}.target`);
  const errorId = `target-${index}-error`;
  const inputId = `target-${index}`;
  const importanceId = `importance-${index}`;

  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem_10rem_auto] sm:items-end">
      <p className="font-medium sm:pb-2">{label}</p>
      <div>
        <label className={labelClass} htmlFor={inputId}>
          Target for {label}
        </label>
        <input
          id={inputId}
          inputMode="numeric"
          autoComplete="off"
          className={inputClass}
          aria-invalid={Boolean(message)}
          aria-describedby={message ? errorId : `${inputId}-hint`}
          {...registration(`targets.${index}.target`)}
        />
        <p id={`${inputId}-hint`} className="mt-1 text-sm text-stone-600">
          Whole number from {RATING_MIN} to {RATING_MAX}.
        </p>
        <FieldMessage id={errorId} message={message} />
      </div>
      <div>
        <label className={labelClass} htmlFor={importanceId}>
          Importance for {label}
        </label>
        <select id={importanceId} className={inputClass} {...registration(`targets.${index}.importance`)}>
          {importanceLevels.map((level) => (
            <option key={level} value={level}>
              {choiceLabel(level)}
            </option>
          ))}
        </select>
      </div>
      <button type="button" className={buttonClass} onClick={onRemove}>
        Remove {label}
      </button>
    </div>
  );
}
