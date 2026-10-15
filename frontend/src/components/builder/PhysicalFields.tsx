import { useEffect } from "react";

import { choiceLabel } from "../../lib/format.ts";
import { INCH_MAX, INCH_MIN, POUND_MAX, POUND_MIN, type Catalog } from "../../lib/validation/draft.ts";
import { inputClass, labelClass, panelClass } from "../styles.ts";
import { describedBy, fieldMessage, FieldMessage, type BuilderControl } from "./form.tsx";

export function PhysicalFields({ form, catalog }: { form: BuilderControl; catalog: Catalog }) {
  const { register, watch, setValue, formState } = form;
  const errors = formState.errors;

  return (
    <section aria-labelledby="body-heading" className={panelClass}>
      <h2 id="body-heading" className="text-xl font-semibold">
        Body
      </h2>
      <p className="mt-2 text-sm text-stone-700">
        Leave a field on Any, enter a preference, or lock a value. A locked field is
        exact. No height, weight, or wingspan range is verified for the loaded ruleset.
        The number boxes stop at the API limit.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <ChoiceField
          form={form}
          name="buildType"
          lockName="buildTypeLocked"
          label="Build type"
          emptyLabel="Any"
          options={catalog.buildTypes.map((id) => ({ id, label: choiceLabel(id) }))}
        />
        <ChoiceField
          form={form}
          name="position"
          lockName="positionLocked"
          label="Position"
          emptyLabel="Any"
          options={catalog.positions.map((id) => ({ id, label: id }))}
        />
        <NumberField
          id="height"
          label="Height (inches)"
          hint={`Whole inches from ${INCH_MIN} to ${INCH_MAX}. That ceiling is the API limit, not a verified in-game range.`}
          value={watch("height")}
          locked={watch("heightLocked")}
          message={fieldMessage(errors, "height")}
          registration={register("height")}
          lockRegistration={register("heightLocked")}
          onClearLock={() => setValue("heightLocked", false, { shouldValidate: true })}
        />
        <NumberField
          id="weight"
          label="Weight (pounds)"
          hint={`Whole pounds from ${POUND_MIN} to ${POUND_MAX}. That ceiling is the API limit, not a verified in-game range.`}
          value={watch("weight")}
          locked={watch("weightLocked")}
          message={fieldMessage(errors, "weight")}
          registration={register("weight")}
          lockRegistration={register("weightLocked")}
          onClearLock={() => setValue("weightLocked", false, { shouldValidate: true })}
        />
        <NumberField
          id="wingspan"
          label="Wingspan (inches)"
          hint={`Whole inches from ${INCH_MIN} to ${INCH_MAX}. That ceiling is the API limit, not a verified in-game range.`}
          value={watch("wingspan")}
          locked={watch("wingspanLocked")}
          message={fieldMessage(errors, "wingspan")}
          registration={register("wingspan")}
          lockRegistration={register("wingspanLocked")}
          onClearLock={() => setValue("wingspanLocked", false, { shouldValidate: true })}
        />
      </div>
    </section>
  );
}

function ChoiceField({
  form,
  name,
  lockName,
  label,
  emptyLabel,
  options,
}: {
  form: BuilderControl;
  name: "buildType" | "position";
  lockName: "buildTypeLocked" | "positionLocked";
  label: string;
  emptyLabel: string;
  options: { id: string; label: string }[];
}) {
  const { register, watch, setValue, formState } = form;
  const value = watch(name);
  const locked = watch(lockName);
  const message = fieldMessage(formState.errors, name);
  const errorId = `${name}-error`;

  useEffect(() => {
    if (value === "" && locked) {
      setValue(lockName, false, { shouldValidate: true });
    }
  }, [lockName, locked, setValue, value]);

  const field = register(name);

  return (
    <div>
      <label className={labelClass} htmlFor={name}>
        {label}
      </label>
      <select
        id={name}
        className={inputClass}
        aria-invalid={Boolean(message)}
        aria-describedby={message ? errorId : undefined}
        {...field}
        onChange={(event) => {
          if (event.target.value === "" && locked) {
            setValue(lockName, false, { shouldValidate: false });
          }
          void field.onChange(event);
        }}
      >
        <option value="">{emptyLabel}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      <label className="mt-2 flex items-center gap-2 text-sm text-stone-800">
        <input type="checkbox" {...register(lockName)} disabled={value === ""} />
        Lock {label.toLowerCase()}
      </label>
      <LockState value={value} locked={locked} />
      <FieldMessage id={errorId} message={message} />
    </div>
  );
}

function NumberField({
  id,
  label,
  hint,
  value,
  locked,
  message,
  registration,
  lockRegistration,
  onClearLock,
}: {
  id: "height" | "weight" | "wingspan";
  label: string;
  hint: string;
  value: string;
  locked: boolean;
  message?: string;
  registration: ReturnType<BuilderControl["register"]>;
  lockRegistration: ReturnType<BuilderControl["register"]>;
  onClearLock: () => void;
}) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  useEffect(() => {
    if (value.trim() === "" && locked) {
      onClearLock();
    }
  }, [locked, onClearLock, value]);

  return (
    <div>
      <label className={labelClass} htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        inputMode="numeric"
        autoComplete="off"
        className={inputClass}
        aria-invalid={Boolean(message)}
        aria-describedby={describedBy(errorId, message, hintId)}
        {...registration}
        onChange={(event) => {
          if (event.target.value.trim() === "" && locked) {
            onClearLock();
          }
          void registration.onChange(event);
        }}
      />
      <p id={hintId} className="mt-1 text-sm text-stone-600">
        {hint}
      </p>
      <label className="mt-2 flex items-center gap-2 text-sm text-stone-800">
        <input type="checkbox" {...lockRegistration} disabled={value.trim() === ""} />
        Lock {label.toLowerCase()}
      </label>
      <LockState value={value.trim()} locked={locked} />
      <FieldMessage id={errorId} message={message} />
    </div>
  );
}

function LockState({ value, locked }: { value: string; locked: boolean }) {
  if (!value) {
    return null;
  }
  return <p className="mt-1 text-sm text-stone-700">{locked ? "Locked." : "Preferred. The search may choose another value."}</p>;
}
