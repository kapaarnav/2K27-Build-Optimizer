import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CoverageStatus } from "./CoverageStatus.tsx";

const coverage = {
  rulesetId: "nba2k27-unverified",
  recommendationsEnabled: false,
  notes: ["No verified NBA 2K27 rules are loaded. Public build recommendations are disabled."],
  disclaimer: "Unofficial NBA 2K27 build planning tool.",
};

describe("CoverageStatus", () => {
  it("shows a loading status", () => {
    render(<CoverageStatus state="loading" />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking verified coverage");
  });

  it("shows that recommendations are off", () => {
    render(<CoverageStatus state="success" coverage={coverage} />);
    expect(screen.getByText("Recommendations off")).toBeInTheDocument();
    expect(screen.getByText(/No verified NBA 2K27 rules are loaded/)).toBeInTheDocument();
  });

  it("shows a reachable error and retries", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<CoverageStatus state="error" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Service unreachable");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
