import type { OptimizeRequest, Recommendation } from "../../lib/api/client.ts";
import { choiceLabel, formatInches, formatScore, formatWeight } from "../../lib/format.ts";
import { attributeLabel, type Catalog } from "../../lib/validation/draft.ts";
import { buttonClass, panelClass } from "../styles.ts";

export function ResultCard({
  build,
  catalog,
  request,
  compared,
  compareDisabled,
  overlap,
  onToggleCompare,
  onRefine,
}: {
  build: Recommendation;
  catalog: Catalog | null;
  request: OptimizeRequest | null;
  compared: boolean;
  compareDisabled: boolean;
  overlap: boolean;
  onToggleCompare: () => void;
  onRefine: () => void;
}) {
  const label = (id: string) => (catalog ? attributeLabel(catalog, id) : id);
  const applications = build.cap_breaker_allocations.reduce((sum, item) => sum + item.applications, 0);
  const gain = build.cap_breaker_allocations.reduce((sum, item) => sum + item.rating_gain, 0);
  const reason =
    build.deviations[0]?.message ||
    build.score_breakdown.components?.find((component) => component.note)?.note ||
    "Ranked by the request's priorities.";

  return (
    <article aria-labelledby={`build-${build.build_id}`} className={panelClass}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-stone-600">Rank {build.rank}</p>
          <h3 id={`build-${build.build_id}`} className="mt-1 text-xl font-semibold">
            {build.name}
          </h3>
        </div>
        <p className="text-right">
          <span className="text-2xl font-semibold">{formatScore(build.score)}</span>
          <span className="mt-1 block text-sm text-stone-600">fit for this request</span>
        </p>
      </div>
      {overlap ? (
        <p className="mt-2 text-sm text-stone-700">Also listed in the top optimized builds.</p>
      ) : null}
      <p className="mt-3 text-sm text-stone-800">
        {build.body.position} · {choiceLabel(build.body.build_type)} · {formatInches(build.body.height_in)} ·{" "}
        {formatWeight(build.body.weight_lb)} · wingspan {formatInches(build.body.wingspan_in)}
      </p>
      <p className="mt-2 text-sm text-stone-800">
        Cap Breakers: {applications} applications, {gain} total rating gain.
      </p>
      <p className="mt-2 text-sm text-stone-700">{reason}</p>
      <p className="mt-2 text-sm text-stone-600">Rules check: {build.verification}.</p>
      {request && request.attribute_targets.length > 0 ? (
        <ul className="mt-3 grid gap-1 text-sm text-stone-800 sm:grid-cols-2">
          {request.attribute_targets.map((target) => {
            const final = build.final_attributes.find((item) => item.id === target.id);
            return (
              <li key={target.id}>
                {label(target.id)}: requested {target.target} {choiceLabel(target.importance)}, final{" "}
                {final ? final.rating : "—"}
              </li>
            );
          })}
        </ul>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-3">
        <label className="flex items-center gap-2 text-sm text-stone-800">
          <input
            type="checkbox"
            checked={compared}
            disabled={compareDisabled && !compared}
            onChange={onToggleCompare}
          />
          Compare {build.name}
        </label>
        <button type="button" className={buttonClass} onClick={onRefine}>
          Refine this build
        </button>
      </div>
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-semibold">Full build</summary>
        <div className="mt-3 space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <caption className="sr-only">Attributes for {build.name}</caption>
              <thead>
                <tr className="border-b border-stone-200 text-stone-600">
                  <th scope="col" className="py-2 pr-3 font-medium">Attribute</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Base</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Cap Breaker gain</th>
                  <th scope="col" className="py-2 font-medium">Final</th>
                </tr>
              </thead>
              <tbody>
                {attributeIds(build).map((id) => (
                  <tr key={id} className="border-b border-stone-100">
                    <th scope="row" className="py-2 pr-3 font-medium">{label(id)}</th>
                    <td className="py-2 pr-3">{ratingOf(build.base_attributes, id)}</td>
                    <td className="py-2 pr-3">{gainOf(build, id)}</td>
                    <td className="py-2">{ratingOf(build.final_attributes, id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <AllocationList build={build} label={label} />
          <EligibilityList title="Eligible badges" items={build.eligible_badges.map((item) => `${item.id} (${choiceLabel(item.highest_tier)})`)} />
          <EligibilityList title="Eligible animations" items={build.eligible_animations.map((item) => item.id)} />
          <EligibilityList title="Eligible Takeovers" items={build.eligible_takeovers.map((item) => item.id)} />
          <div>
            <h4 className="text-sm font-semibold">Score breakdown</h4>
            <p className="mt-1 text-sm text-stone-600">
              {build.score_breakdown.scoring_version}. A high score means a strong fit for this request.
            </p>
            <ul className="mt-2 space-y-1 text-sm text-stone-800">
              {(build.score_breakdown.components ?? []).length === 0 ? (
                <li>No score components were returned.</li>
              ) : (
                build.score_breakdown.components?.map((component) => (
                  <li key={component.id}>
                    {component.id}: value {component.value}, weight {component.weight}
                    {component.note ? `. ${component.note}` : ""}
                  </li>
                ))
              )}
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-semibold">Deviations</h4>
            {(build.deviations ?? []).length === 0 ? (
              <p className="mt-1 text-sm text-stone-700">No requested rating moved.</p>
            ) : (
              <ul className="mt-1 list-disc pl-5 text-sm text-stone-800">
                {build.deviations.map((deviation) => (
                  <li key={`${deviation.attribute_id}-${deviation.message}`}>{deviation.message}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </details>
    </article>
  );
}

function attributeIds(build: Recommendation): string[] {
  const ids = build.final_attributes.map((item) => item.id);
  for (const item of build.base_attributes) {
    if (!ids.includes(item.id)) {
      ids.push(item.id);
    }
  }
  return ids;
}

function ratingOf(ratings: { id: string; rating: number }[], id: string): string {
  const match = ratings.find((item) => item.id === id);
  return match ? String(match.rating) : "—";
}

function gainOf(build: Recommendation, id: string): string {
  const rows = build.cap_breaker_allocations.filter((item) => item.attribute_id === id);
  if (rows.length === 0) {
    return "—";
  }
  return String(rows.reduce((sum, item) => sum + item.rating_gain, 0));
}

function AllocationList({
  build,
  label,
}: {
  build: Recommendation;
  label: (id: string) => string;
}) {
  return (
    <div>
      <h4 className="text-sm font-semibold">Cap Breaker allocations</h4>
      {build.cap_breaker_allocations.length === 0 ? (
        <p className="mt-1 text-sm text-stone-700">No Cap Breakers spent.</p>
      ) : (
        <ul className="mt-1 list-disc pl-5 text-sm text-stone-800">
          {build.cap_breaker_allocations.map((item) => (
            <li key={`${item.pool_id}-${item.attribute_id}`}>
              {item.pool_id} on {label(item.attribute_id)}: {item.applications} applications, {item.rating_gain}{" "}
              rating gain
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EligibilityList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4 className="text-sm font-semibold">{title}</h4>
      {items.length === 0 ? (
        <p className="mt-1 text-sm text-stone-700">None reported.</p>
      ) : (
        <ul className="mt-1 list-disc pl-5 text-sm text-stone-800">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
