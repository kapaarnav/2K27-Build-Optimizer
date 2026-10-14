import { useQuery } from "@tanstack/react-query";

import { CoverageStatus } from "../components/CoverageStatus.tsx";
import { getMetadata } from "../lib/api/client.ts";

export function HomePage() {
  const metadata = useQuery({
    queryKey: ["metadata"],
    queryFn: getMetadata,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Build planner</h1>
        <p className="mt-3 text-stone-700">
          Describe the MyPLAYER you want. Recommendations appear only after the
          matching builder rules have been verified in game.
        </p>
      </div>
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
        Unofficial NBA 2K27 build planning tool. Not affiliated with or endorsed by 2K
        or the NBA.
      </p>
      {metadata.isPending ? <CoverageStatus state="loading" /> : null}
      {metadata.isError ? (
        <CoverageStatus state="error" onRetry={() => void metadata.refetch()} />
      ) : null}
      {metadata.data ? (
        <CoverageStatus
          state="success"
          coverage={{
            rulesetId: metadata.data.ruleset_id,
            recommendationsEnabled: metadata.data.recommendations_enabled,
            notes: metadata.data.notes ?? [],
            disclaimer: metadata.data.disclaimer,
          }}
        />
      ) : null}
    </div>
  );
}
