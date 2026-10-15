import type { Recommendation } from "../../lib/api/client.ts";
import { choiceLabel, formatInches, formatScore, formatWeight } from "../../lib/format.ts";
import { attributeLabel, type Catalog } from "../../lib/validation/draft.ts";
import { buttonClass, panelClass } from "../styles.ts";

export function CompareView({
  builds,
  catalog,
  onRemove,
}: {
  builds: Recommendation[];
  catalog: Catalog | null;
  onRemove: (buildId: string) => void;
}) {
  const label = (id: string) => (catalog ? attributeLabel(catalog, id) : id);
  const attributeList = uniqueAttributes(builds);
  const badgeList = uniqueIds(builds.flatMap((build) => build.eligible_badges.map((item) => item.id)));

  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-700">
        Highlighted rows differ across the selected builds. The score is a fit for the request
        that produced each build.
      </p>
      <div className="grid gap-4 lg:grid-cols-3">
        {builds.map((build) => (
          <article key={build.build_id} aria-labelledby={`compare-${build.build_id}`} className={panelClass}>
            <h2 id={`compare-${build.build_id}`} className="text-lg font-semibold">
              {build.name}
            </h2>
            <p className="mt-1 text-sm text-stone-600">
              Rank {build.rank} · {formatScore(build.score)} fit for this request
            </p>
            <dl className="mt-3 space-y-2 text-sm">
              <CompareRow
                term="Body"
                value={`${build.body.position}, ${choiceLabel(build.body.build_type)}, ${formatInches(build.body.height_in)}, ${formatWeight(build.body.weight_lb)}, wingspan ${formatInches(build.body.wingspan_in)}`}
                differs={bodiesDiffer(builds)}
              />
              {attributeList.map((id) => (
                <CompareRow
                  key={id}
                  term={label(id)}
                  value={finalOf(build, id)}
                  differs={finalsDiffer(builds, id)}
                />
              ))}
            </dl>
            <h3 className="mt-4 text-sm font-semibold">Badges</h3>
            <ul className="mt-1 space-y-1 text-sm">
              {badgeList.length === 0 ? (
                <li className="text-stone-700">None reported.</li>
              ) : (
                badgeList.map((id) => {
                  const present = build.eligible_badges.some((item) => item.id === id);
                  const differs = builds.some((item) => item.eligible_badges.some((badge) => badge.id === id)) &&
                    builds.some((item) => !item.eligible_badges.some((badge) => badge.id === id));
                  return (
                    <li key={id} className={differs ? "rounded bg-amber-50 px-2 py-1" : "px-2 py-1"}>
                      {present ? id : `${id}: absent`}
                      {differs ? <span className="sr-only">, differs</span> : null}
                    </li>
                  );
                })
              )}
            </ul>
            <h3 className="mt-4 text-sm font-semibold">Cap Breakers</h3>
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
            <button type="button" className={`${buttonClass} mt-4`} onClick={() => onRemove(build.build_id)}>
              Remove {build.name} from compare
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}

function CompareRow({ term, value, differs }: { term: string; value: string; differs: boolean }) {
  return (
    <div className={differs ? "rounded bg-amber-50 px-2 py-1" : "px-2 py-1"}>
      <dt className="font-medium text-stone-700">{term}</dt>
      <dd>
        {value}
        {differs ? <span className="sr-only">, differs</span> : null}
      </dd>
    </div>
  );
}

function uniqueAttributes(builds: Recommendation[]): string[] {
  const ids: string[] = [];
  for (const build of builds) {
    for (const item of [...build.final_attributes, ...build.base_attributes]) {
      if (!ids.includes(item.id)) {
        ids.push(item.id);
      }
    }
  }
  return ids;
}

function uniqueIds(ids: string[]): string[] {
  return [...new Set(ids)];
}

function finalOf(build: Recommendation, id: string): string {
  const match = build.final_attributes.find((item) => item.id === id);
  return match ? String(match.rating) : "—";
}

function finalsDiffer(builds: Recommendation[], id: string): boolean {
  return new Set(builds.map((build) => finalOf(build, id))).size > 1;
}

function bodiesDiffer(builds: Recommendation[]): boolean {
  const signatures = builds.map(
    (build) =>
      `${build.body.build_type}|${build.body.position}|${build.body.height_in}|${build.body.weight_lb}|${build.body.wingspan_in}`,
  );
  return new Set(signatures).size > 1;
}
