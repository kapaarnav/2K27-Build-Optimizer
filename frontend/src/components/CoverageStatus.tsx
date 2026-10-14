export type CoverageView = {
  rulesetId: string;
  recommendationsEnabled: boolean;
  notes: string[];
  disclaimer: string;
};

type CoverageStatusProps =
  | { state: "loading" }
  | { state: "error"; onRetry: () => void }
  | { state: "success"; coverage: CoverageView };

export function CoverageStatus(props: CoverageStatusProps) {
  if (props.state === "loading") {
    return (
      <section
        role="status"
        className="rounded-lg border border-stone-200 bg-white p-5"
      >
        <h2 className="text-lg font-semibold">Checking verified coverage</h2>
        <p className="mt-2 text-stone-700">
          Asking the planning service which rules are verified.
        </p>
      </section>
    );
  }

  if (props.state === "error") {
    return (
      <section
        role="alert"
        className="rounded-lg border border-stone-300 bg-stone-100 p-5"
      >
        <h2 className="text-lg font-semibold">Service unreachable</h2>
        <p className="mt-2 text-stone-800">
          The planning service could not be reached. Start the API and try again.
        </p>
        <button
          type="button"
          onClick={props.onRetry}
          className="mt-4 rounded-md border border-stone-400 bg-white px-3 py-2 text-sm font-medium"
        >
          Retry
        </button>
      </section>
    );
  }

  const label = props.coverage.recommendationsEnabled
    ? "Recommendations on"
    : "Recommendations off";

  return (
    <section
      aria-labelledby="coverage-heading"
      className="rounded-lg border border-stone-200 bg-white p-5"
    >
      <p className="text-sm font-medium uppercase tracking-wide text-stone-600">
        {label}
      </p>
      <h2 id="coverage-heading" className="mt-2 text-lg font-semibold">
        Ruleset {props.coverage.rulesetId}
      </h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-stone-800">
        {props.coverage.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
      <p className="mt-4 text-sm text-stone-600">{props.coverage.disclaimer}</p>
    </section>
  );
}
