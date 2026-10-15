import { Link } from "react-router-dom";

import type { OptimizeRequest, OptimizeResponse, Recommendation } from "../../lib/api/client.ts";
import { formatElapsed } from "../../lib/format.ts";
import type { Catalog } from "../../lib/validation/draft.ts";
import { panelClass } from "../styles.ts";
import { ResultCard } from "./ResultCard.tsx";
import { statusCopy } from "./statusCopy.ts";

export function ResultsView({
  result,
  request,
  catalog,
  compareIds,
  compareNotice,
  onToggleCompare,
  onRefine,
}: {
  result: OptimizeResponse;
  request: OptimizeRequest | null;
  catalog: Catalog | null;
  compareIds: string[];
  compareNotice: string | null;
  onToggleCompare: (buildId: string) => void;
  onRefine: (build: Recommendation) => void;
}) {
  const copy = statusCopy(result.status);
  const top = result.recommendations?.top ?? [];
  const alternatives = result.recommendations?.alternatives ?? [];
  const topIds = new Set(top.map((build) => build.build_id));
  const conflicts = result.status === "infeasible_proven" ? result.conflicts : [];
  const tone =
    result.status === "unsupported" || result.status === "no_feasible_found_in_budget"
      ? "border-amber-200 bg-amber-50"
      : "border-stone-200 bg-white";
  const primaryTitle = result.status === "infeasible_proven" ? "Closest legal options" : "Top optimized builds";

  return (
    <div className="space-y-6">
      <section aria-labelledby="result-status" className={`rounded-lg border px-4 py-4 ${tone}`}>
        <h2 id="result-status" className="text-xl font-semibold">
          {copy.heading}
        </h2>
        <p className="mt-2 text-sm text-stone-800">{copy.body}</p>
        <p className="mt-2 text-sm text-stone-700">
          {result.optimality_proven ? "Ranking proven for this search." : "Ranking is unproven."} Finished in{" "}
          {formatElapsed(result.elapsed_ms)}. Ruleset {result.ruleset_id}.
          {result.cache.hit ? " Read from the search cache." : ""}
        </p>
        {result.coverage.missing_mechanics.length > 0 ? (
          <div className="mt-3">
            <h3 className="text-sm font-semibold">Missing mechanics</h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-stone-800">
              {result.coverage.missing_mechanics.map((mechanic) => (
                <li key={mechanic}>{mechanic}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {result.warnings.length > 0 ? (
          <ul className="mt-3 list-disc pl-5 text-sm text-stone-800">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : null}
      </section>
      {conflicts.length > 0 ? (
        <section aria-labelledby="conflicts-heading" className={panelClass}>
          <h2 id="conflicts-heading" className="text-lg font-semibold">
            Conflicts
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-stone-800">
            {conflicts.map((conflict) => (
              <li key={`${conflict.field}-${conflict.message}`}>{conflict.message}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {(result.unmet_requirements ?? []).length > 0 ? (
        <section aria-labelledby="unmet-heading" className={panelClass}>
          <h2 id="unmet-heading" className="text-lg font-semibold">
            Unmet requirements
          </h2>
          <ul className="mt-2 space-y-2 text-sm text-stone-800">
            {result.unmet_requirements?.map((item) => (
              <li key={`${item.field}-${item.message}`}>
                <p>{item.message}</p>
                <p className="text-stone-600">
                  Requested {item.requested}. Achieved {item.achieved}.
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-stone-700">
        {compareIds.length === 0
          ? "Select up to three builds to compare."
          : compareIds.length >= 3
            ? "Three builds are selected. Remove one to add another."
            : `${compareIds.length} selected for comparison.`}
      </p>
        <Link
          to="/compare"
          className="text-sm font-medium text-stone-900 underline"
        >
          Open compare
        </Link>
      </div>
      {compareNotice ? (
        <p role="status" className="text-sm text-stone-800">
          {compareNotice}
        </p>
      ) : null}
      <BuildSection
        title={primaryTitle}
        builds={top}
        empty={
          result.status === "unsupported"
            ? "No build was returned. The request is outside verified coverage."
            : "No builds in this section."
        }
        catalog={catalog}
        request={request}
        compareIds={compareIds}
        topIds={topIds}
        overlap={false}
        onToggleCompare={onToggleCompare}
        onRefine={onRefine}
      />
      <BuildSection
        title="Distinct alternatives"
        builds={alternatives}
        empty="No distinct alternative was found."
        catalog={catalog}
        request={request}
        compareIds={compareIds}
        topIds={topIds}
        overlap
        onToggleCompare={onToggleCompare}
        onRefine={onRefine}
      />
      <p className="text-sm text-stone-600">
        Sharing and issue reports are not available in this version. A shared link is stored
        only after that feature is turned on. These results stay in this browser tab until you
        refresh the page.
      </p>
    </div>
  );
}

function BuildSection({
  title,
  builds,
  empty,
  catalog,
  request,
  compareIds,
  topIds,
  overlap,
  onToggleCompare,
  onRefine,
}: {
  title: string;
  builds: Recommendation[];
  empty: string;
  catalog: Catalog | null;
  request: OptimizeRequest | null;
  compareIds: string[];
  topIds: Set<string>;
  overlap: boolean;
  onToggleCompare: (buildId: string) => void;
  onRefine: (build: Recommendation) => void;
}) {
  const headingId = title.toLowerCase().replace(/[^a-z]+/g, "-");
  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h2 id={headingId} className="text-xl font-semibold">
        {title}
      </h2>
      {builds.length === 0 ? (
        <p className="text-sm text-stone-700">{empty}</p>
      ) : (
        builds.map((build) => (
          <ResultCard
            key={`${title}-${build.build_id}`}
            build={build}
            catalog={catalog}
            request={request}
            compared={compareIds.includes(build.build_id)}
            compareDisabled={compareIds.length >= 3}
            overlap={overlap && topIds.has(build.build_id)}
            onToggleCompare={() => onToggleCompare(build.build_id)}
            onRefine={() => onRefine(build)}
          />
        ))
      )}
    </section>
  );
}
