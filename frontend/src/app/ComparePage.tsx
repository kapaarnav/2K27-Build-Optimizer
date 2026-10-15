import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { CompareView } from "../components/results/CompareView.tsx";
import { getMetadata } from "../lib/api/client.ts";
import type { Recommendation } from "../lib/api/client.ts";
import { catalogFrom } from "../lib/validation/draft.ts";
import { usePlanner } from "../state/planner.ts";

export function ComparePage() {
  const planner = usePlanner();
  const metadata = useQuery({ queryKey: ["metadata"], queryFn: getMetadata });
  const catalog = metadata.data ? catalogFrom(metadata.data) : null;
  const builds = selectedBuilds(planner.result?.recommendations, planner.compareIds);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Compare</h1>
        <p className="mt-3 text-stone-700">Up to three builds from the latest search, side by side.</p>
      </div>
      {builds.length === 0 ? (
        <div className="rounded-lg border border-stone-200 bg-white p-5">
          <p>Select up to three builds from the latest results.</p>
          <Link to="/results" className="mt-4 inline-block text-sm font-medium underline">
            Go to results
          </Link>
        </div>
      ) : (
        <>
          {builds.length < 2 ? (
            <p className="text-sm text-stone-700">Select one more build to see a comparison.</p>
          ) : null}
          <CompareView builds={builds} catalog={catalog} onRemove={planner.removeCompare} />
        </>
      )}
    </div>
  );
}

function selectedBuilds(
  recommendations: { top?: Recommendation[]; alternatives?: Recommendation[] } | undefined,
  ids: string[],
): Recommendation[] {
  const all = [...(recommendations?.top ?? []), ...(recommendations?.alternatives ?? [])];
  return ids.flatMap((id) => {
    const match = all.find((build) => build.build_id === id);
    return match ? [match] : [];
  });
}
