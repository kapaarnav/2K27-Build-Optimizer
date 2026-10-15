import type { OptimizeResponse } from "../../lib/api/client.ts";

export function statusCopy(status: OptimizeResponse["status"]): { heading: string; body: string } {
  switch (status) {
    case "complete_proven":
      return {
        heading: "Proven ranking",
        body: "The search proved this ranking across the supported bodies.",
      };
    case "partial_feasible":
      return {
        heading: "Partial result",
        body: "These builds passed the rules check. The ranking is unproven because the search ended early.",
      };
    case "unsupported":
      return {
        heading: "Unsupported request",
        body: "Verified rules do not cover this request. In-game legality was not judged.",
      };
    case "infeasible_proven":
      return {
        heading: "Proven infeasible",
        body: "No supported build can meet every required input. Game rules stayed in place.",
      };
    case "no_feasible_found_in_budget":
      return {
        heading: "No valid result found yet",
        body: "The search ended before it found a build. That does not prove the request is impossible.",
      };
  }
}
