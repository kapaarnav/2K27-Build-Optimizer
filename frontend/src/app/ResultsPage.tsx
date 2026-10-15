import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { ResultsView } from "../components/results/ResultsView.tsx";
import { getMetadata } from "../lib/api/client.ts";
import { catalogFrom } from "../lib/validation/draft.ts";
import { usePlanner } from "../state/planner.ts";

export function ResultsPage() {
  const planner = usePlanner();
  const metadata = useQuery({ queryKey: ["metadata"], queryFn: getMetadata });
  const heading = useRef<HTMLHeadingElement>(null);
  const catalog = metadata.data ? catalogFrom(metadata.data) : null;

  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 ref={heading} tabIndex={-1} className="text-3xl font-semibold tracking-tight outline-none">
          Results
        </h1>
        <p className="mt-3 text-stone-700">
          The latest search stays in this tab. Refreshing the page clears it.
        </p>
      </div>
      {planner.result ? (
        <ResultsView
          result={planner.result}
          request={planner.submittedRequest}
          catalog={catalog}
          compareIds={planner.compareIds}
          compareNotice={planner.compareNotice}
          onToggleCompare={planner.toggleCompare}
          onRefine={planner.startRefine}
        />
      ) : (
        <div className="rounded-lg border border-stone-200 bg-white p-5">
          <p>There is no search to show.</p>
          <Link to="/build" className="mt-4 inline-block text-sm font-medium underline">
            Go to the builder
          </Link>
        </div>
      )}
    </div>
  );
}
