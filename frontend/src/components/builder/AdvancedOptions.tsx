import type { ReactNode } from "react";
import { useFieldArray } from "react-hook-form";

import { attributeLabel, POOL_MAX, type Catalog } from "../../lib/validation/draft.ts";
import { choiceLabel } from "../../lib/format.ts";
import { buttonClass, inputClass, labelClass } from "../styles.ts";
import { fieldMessage, FieldMessage, type BuilderControl } from "./form.tsx";

export function AdvancedOptions({ form, catalog }: { form: BuilderControl; catalog: Catalog }) {
  return (
    <details className="rounded-lg border border-stone-200 bg-white p-5">
      <summary className="cursor-pointer text-xl font-semibold">Cap Breakers and unlocks</summary>
      <div className="mt-4 space-y-8">
        <CapBreakers form={form} catalog={catalog} />
        <UnlockRequests form={form} catalog={catalog} />
      </div>
    </details>
  );
}

function CapBreakers({ form, catalog }: { form: BuilderControl; catalog: Catalog }) {
  const { register, control, watch, setValue, formState } = form;
  const pools = useFieldArray({ control, name: "specializationPools", keyName: "fieldKey" });
  const minimums = useFieldArray({ control, name: "minimumAllocations", keyName: "fieldKey" });
  const forbidden = watch("forbiddenAttributeIds");
  const usedCategories = new Set(pools.fields.map((pool) => pool.category));
  const openCategories = catalog.categories.filter((category) => !usedCategories.has(category));

  return (
    <fieldset>
      <legend className="text-lg font-semibold">Cap Breakers</legend>
      <p className="mt-2 text-sm text-stone-700">
        Enter the pools you have. Counts are inventory for this search. A verified ruleset
        still has to describe Cap Breaker gains before a result can spend them.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label className={labelClass} htmlFor="unrestricted-available">
            Unrestricted pool
          </label>
          <input
            id="unrestricted-available"
            inputMode="numeric"
            autoComplete="off"
            className={inputClass}
            aria-describedby="unrestricted-hint"
            {...register("unrestrictedAvailable")}
          />
          <p id="unrestricted-hint" className="mt-1 text-sm text-stone-600">
            Blank or 0 sends no unrestricted pool. The request id is unrestricted.
          </p>
          <FieldMessage
            id="unrestricted-error"
            message={fieldMessage(formState.errors, "unrestrictedAvailable")}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="reserved-total">
            Reserve count
          </label>
          <input
            id="reserved-total"
            inputMode="numeric"
            autoComplete="off"
            className={inputClass}
            {...register("reservedTotal")}
          />
          <FieldMessage id="reserved-error" message={fieldMessage(formState.errors, "reservedTotal")} />
        </div>
      </div>
      <div className="mt-4">
        <h3 className="text-sm font-semibold text-stone-800">Specialization pools</h3>
        {catalog.categories.length === 0 ? (
          <p className="mt-1 text-sm text-stone-700">
            Specialization categories come from verified attributes. None are loaded.
          </p>
        ) : (
          <>
            <ul className="mt-2 space-y-3">
              {pools.fields.map((pool, index) => (
                <li key={pool.fieldKey} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem_auto] sm:items-end">
                  <div>
                    <label className={labelClass} htmlFor={`spec-category-${index}`}>
                      Category
                    </label>
                    <select
                      id={`spec-category-${index}`}
                      className={inputClass}
                      {...register(`specializationPools.${index}.category`)}
                    >
                      {catalog.categories.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className={labelClass} htmlFor={`spec-count-${index}`}>
                      Available
                    </label>
                    <input
                      id={`spec-count-${index}`}
                      inputMode="numeric"
                      autoComplete="off"
                      className={inputClass}
                      {...register(`specializationPools.${index}.available`)}
                    />
                    <FieldMessage
                      id={`spec-count-${index}-error`}
                      message={fieldMessage(formState.errors, `specializationPools.${index}.available`)}
                    />
                  </div>
                  <button type="button" className={buttonClass} onClick={() => pools.remove(index)}>
                    Remove specialization pool
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className={`${buttonClass} mt-3`}
              disabled={openCategories.length === 0}
              onClick={() =>
                pools.append({
                  key: crypto.randomUUID(),
                  category: openCategories[0] ?? catalog.categories[0] ?? "",
                  available: "",
                })
              }
            >
              Add specialization pool
            </button>
          </>
        )}
      </div>
      <div className="mt-4">
        <h3 className="text-sm font-semibold text-stone-800">Forbidden attributes</h3>
        {catalog.attributes.length === 0 ? (
          <p className="mt-1 text-sm text-stone-700">No verified attributes to forbid.</p>
        ) : (
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {catalog.attributes.map((attribute) => (
              <li key={attribute.id}>
                <label className="flex items-center gap-2 text-sm text-stone-800">
                  <input
                    type="checkbox"
                    checked={forbidden.includes(attribute.id)}
                    onChange={(event) => {
                      const next = event.target.checked
                        ? [...forbidden, attribute.id]
                        : forbidden.filter((id) => id !== attribute.id);
                      setValue("forbiddenAttributeIds", next, { shouldValidate: true });
                    }}
                  />
                  Forbid {attribute.label}
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="mt-4">
        <h3 className="text-sm font-semibold text-stone-800">Minimum allocations</h3>
        <ul className="mt-2 space-y-3">
          {minimums.fields.map((row, index) => (
            <li key={row.fieldKey} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem_auto] sm:items-end">
              <div>
                <label className={labelClass} htmlFor={`minimum-attribute-${index}`}>
                  Attribute
                </label>
                <select
                  id={`minimum-attribute-${index}`}
                  className={inputClass}
                  {...register(`minimumAllocations.${index}.attributeId`)}
                >
                  {catalog.attributes.map((attribute) => (
                    <option key={attribute.id} value={attribute.id}>
                      {attribute.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelClass} htmlFor={`minimum-count-${index}`}>
                  Minimum count
                </label>
                <input
                  id={`minimum-count-${index}`}
                  inputMode="numeric"
                  autoComplete="off"
                  className={inputClass}
                  {...register(`minimumAllocations.${index}.count`)}
                />
              </div>
              <button type="button" className={buttonClass} onClick={() => minimums.remove(index)}>
                Remove minimum for {attributeLabel(catalog, row.attributeId)}
              </button>
            </li>
          ))}
        </ul>
        <FieldMessage
          id="minimums-error"
          message={fieldMessage(formState.errors, "minimumAllocations")}
        />
        <button
          type="button"
          className={`${buttonClass} mt-3`}
          disabled={catalog.attributes.length === 0}
          onClick={() =>
            minimums.append({
              attributeId: catalog.attributes[0]?.id ?? "",
              count: "1",
            })
          }
        >
          Add minimum allocation
        </button>
        <p className="mt-2 text-sm text-stone-600">Each count is from 0 to {POOL_MAX}.</p>
      </div>
    </fieldset>
  );
}

function UnlockRequests({ form, catalog }: { form: BuilderControl; catalog: Catalog }) {
  const badges = useFieldArray({ control: form.control, name: "badges", keyName: "fieldKey" });
  const animations = useFieldArray({ control: form.control, name: "animations", keyName: "fieldKey" });
  const takeovers = useFieldArray({ control: form.control, name: "takeovers", keyName: "fieldKey" });
  const importance = catalog.importanceLevels.includes("normal")
    ? "normal"
    : (catalog.importanceLevels[0] ?? "normal");
  const tier = catalog.badgeTiers[0] ?? "bronze";

  return (
    <div className="space-y-6">
      <UnlockBlock
        title="Badges"
        empty="No verified badges are in this ruleset."
        addLabel="Add badge"
        catalog={catalog.badges}
        rows={badges.fields}
        onAdd={(id) => badges.append({ id, minimumTier: tier, importance })}
        onRemove={badges.remove}
        renderRow={(row, index) => (
          <>
            <label className={labelClass} htmlFor={`badge-tier-${index}`}>
              Minimum tier for {row.id}
            </label>
            <select id={`badge-tier-${index}`} className={inputClass} {...form.register(`badges.${index}.minimumTier`)}>
              {catalog.badgeTiers.map((item) => (
                <option key={item} value={item}>
                  {choiceLabel(item)}
                </option>
              ))}
            </select>
            <label className={labelClass} htmlFor={`badge-importance-${index}`}>
              Importance for {row.id}
            </label>
            <select
              id={`badge-importance-${index}`}
              className={inputClass}
              {...form.register(`badges.${index}.importance`)}
            >
              {catalog.importanceLevels.map((item) => (
                <option key={item} value={item}>
                  {choiceLabel(item)}
                </option>
              ))}
            </select>
          </>
        )}
      />
      <UnlockBlock
        title="Animations"
        empty="No verified animations are in this ruleset."
        addLabel="Add animation"
        catalog={catalog.animations}
        rows={animations.fields}
        onAdd={(id) => animations.append({ id, importance })}
        onRemove={animations.remove}
        renderRow={(row, index) => (
          <>
            <label className={labelClass} htmlFor={`animation-importance-${index}`}>
              Importance for {row.id}
            </label>
            <select
              id={`animation-importance-${index}`}
              className={inputClass}
              {...form.register(`animations.${index}.importance`)}
            >
              {catalog.importanceLevels.map((item) => (
                <option key={item} value={item}>
                  {choiceLabel(item)}
                </option>
              ))}
            </select>
          </>
        )}
      />
      <UnlockBlock
        title="Takeovers"
        empty="No verified Takeovers are in this ruleset."
        addLabel="Add Takeover"
        catalog={catalog.takeovers}
        rows={takeovers.fields}
        onAdd={(id) => takeovers.append({ id, importance })}
        onRemove={takeovers.remove}
        renderRow={(row, index) => (
          <>
            <label className={labelClass} htmlFor={`takeover-importance-${index}`}>
              Importance for {row.id}
            </label>
            <select
              id={`takeover-importance-${index}`}
              className={inputClass}
              {...form.register(`takeovers.${index}.importance`)}
            >
              {catalog.importanceLevels.map((item) => (
                <option key={item} value={item}>
                  {choiceLabel(item)}
                </option>
              ))}
            </select>
          </>
        )}
      />
    </div>
  );
}

function UnlockBlock<T extends { id: string; fieldKey: string }>({
  title,
  empty,
  addLabel,
  catalog,
  rows,
  onAdd,
  onRemove,
  renderRow,
}: {
  title: string;
  empty: string;
  addLabel: string;
  catalog: { id: string; label: string }[];
  rows: T[];
  onAdd: (id: string) => void;
  onRemove: (index: number) => void;
  renderRow: (row: T, index: number) => ReactNode;
}) {
  const remaining = catalog.filter((item) => !rows.some((row) => row.id === item.id));
  return (
    <section aria-labelledby={`${title}-heading`}>
      <h3 id={`${title}-heading`} className="text-lg font-semibold">
        {title}
      </h3>
      {catalog.length === 0 ? (
        <p className="mt-1 text-sm text-stone-700">{empty}</p>
      ) : (
        <>
          <ul className="mt-2 space-y-3">
            {rows.map((row, index) => (
              <li key={row.fieldKey} className="rounded-md border border-stone-200 p-3">
                <p className="font-medium">{catalog.find((item) => item.id === row.id)?.label ?? row.id}</p>
                <div className="mt-2 grid gap-3 sm:grid-cols-2">{renderRow(row, index)}</div>
                <button type="button" className={`${buttonClass} mt-3`} onClick={() => onRemove(index)}>
                  Remove {row.id}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className={`${buttonClass} mt-3`}
            disabled={remaining.length === 0}
            onClick={() => {
              const next = remaining[0];
              if (next) {
                onAdd(next.id);
              }
            }}
          >
            {addLabel}
          </button>
        </>
      )}
    </section>
  );
}
