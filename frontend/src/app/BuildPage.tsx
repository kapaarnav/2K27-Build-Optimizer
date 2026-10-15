import { useQuery } from "@tanstack/react-query";

import { CoverageStatus } from "../components/CoverageStatus.tsx";
import { BuilderForm } from "../components/builder/BuilderForm.tsx";
import { getMetadata } from "../lib/api/client.ts";

export function BuildPage() {
  const metadata = useQuery({
    queryKey: ["metadata"],
    queryFn: getMetadata,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Builder</h1>
        <p className="mt-3 text-stone-700">
          Set the ratings you want, then generate. Unspecified attributes stay blank
          until a verified catalog lists them.
        </p>
      </div>
      {metadata.isPending ? <CoverageStatus state="loading" /> : null}
      {metadata.isError ? (
        <CoverageStatus state="error" onRetry={() => void metadata.refetch()} />
      ) : null}
      {metadata.data ? <BuilderForm metadata={metadata.data} /> : null}
    </div>
  );
}
