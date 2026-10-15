import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "../App.tsx";
import type { MetadataResponse, OptimizeResponse, ValidateResponse } from "../lib/api/client.ts";
import type { Recommendation } from "../lib/api/client.ts";

function metadata(overrides: Partial<MetadataResponse> = {}): MetadataResponse {
  return {
    ruleset_id: "nba2k27-unverified",
    game: "nba2k27",
    scoring_version: "score-m3",
    optimizer_version: "optimizer-m3-multi-body",
    files_sha256: "a".repeat(64),
    disclaimer: "Unofficial NBA 2K27 build planning tool.",
    recommendations_enabled: false,
    positions: ["PG", "SG", "SF", "PF", "C"],
    build_types: ["male", "female"],
    importance_levels: ["required", "prioritized", "normal"],
    playstyles: [
      { id: "automatic", label: "Automatic" },
      { id: "balanced", label: "Balanced" },
    ],
    attributes: [],
    badges: [],
    animations: [],
    takeovers: [],
    badge_tiers: ["bronze", "silver", "gold", "hall_of_fame"],
    coverage: [],
    notes: ["No verified NBA 2K27 rules are loaded."],
    ...overrides,
  };
}

const fixtureAttributes = [
  { id: "fixture_shot", label: "Fixture shot", category: "fixture_shooting" },
  { id: "fixture_handle", label: "Fixture handle", category: "fixture_play" },
];

function recommendation(id: string, finalShot: number): Recommendation {
  return {
    build_id: id,
    name: `Fixture ${id}`,
    rank: 1,
    score: 90,
    body: {
      build_type: "male",
      position: "PG",
      height_in: 76,
      weight_lb: 180,
      wingspan_in: 80,
    },
    base_attributes: [
      { id: "fixture_shot", rating: 80 },
      { id: "fixture_handle", rating: 70 },
    ],
    final_attributes: [
      { id: "fixture_shot", rating: finalShot },
      { id: "fixture_handle", rating: 70 },
    ],
    cap_breaker_allocations: [
      {
        pool_id: "unrestricted",
        attribute_id: "fixture_shot",
        applications: 2,
        rating_gain: 4,
      },
    ],
    eligible_badges: [{ id: "fixture_badge", highest_tier: "gold" }],
    eligible_animations: [],
    eligible_takeovers: [],
    score_breakdown: {
      scoring_version: "score-m3",
      components: [{ id: "fit", weight: 1, value: 90, note: "Matched the request." }],
    },
    deviations: [],
    verification: "verified",
  };
}

function response(
  status: OptimizeResponse["status"],
  builds: Recommendation[] = [],
): OptimizeResponse {
  const base = {
    request_id: "req_test",
    ruleset_id: "nba2k27-unverified",
    scoring_version: "score-m3",
    optimizer_version: "optimizer-m3-multi-body",
    elapsed_ms: 40,
    coverage: {
      supported: status !== "unsupported",
      notes: [],
      missing_mechanics: status === "unsupported" ? ["attribute_costs"] : [],
    },
    warnings: status === "partial_feasible" ? ["Search ended before every body was proved."] : [],
    cache: { hit: false },
    recommendations: { top: builds, alternatives: [] as Recommendation[] },
    unmet_requirements: [],
  };
  if (status === "infeasible_proven") {
    return {
      ...base,
      status,
      optimality_proven: true,
      conflicts: [{ field: "fixture_shot", message: "Required 99 cannot be reached." }],
      unmet_requirements: [
        {
          field: "fixture_shot",
          requested: "99",
          achieved: "95",
          message: "Fixture shot finished at 95.",
        },
      ],
    };
  }
  if (status === "complete_proven" || status === "partial_feasible") {
    return { ...base, status, optimality_proven: status === "complete_proven" };
  }
  return { ...base, status, optimality_proven: false };
}

const validation: ValidateResponse = {
  request_id: "req_validate",
  ruleset_id: "nba2k27-unverified",
  supported: false,
  issues: [
    {
      field: "coverage",
      code: "coverage_unsupported",
      message: "Verified rules do not cover this request, so in-game legality was not judged.",
    },
  ],
  warnings: ["No verified NBA 2K27 rules are loaded."],
};

function installApi(options: { metadata: MetadataResponse; optimize?: OptimizeResponse }) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.endsWith("/api/v1/metadata")) {
        return Response.json(options.metadata);
      }
      if (url.endsWith("/api/v1/validate")) {
        return Response.json(validation);
      }
      if (url.endsWith("/api/v1/optimize")) {
        return Response.json(options.optimize ?? response("unsupported"));
      }
      return new Response("missing", { status: 404 });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function addShot(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Add Fixture shot" }));
  await user.type(screen.getByLabelText("Target for Fixture shot"), "80");
}

describe("builder", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("keeps an empty catalog empty and blocks generate", async () => {
    installApi({ metadata: metadata() });
    renderAt("/build");
    expect(await screen.findByText(/No verified attributes are in this ruleset/)).toBeInTheDocument();
    expect(screen.getByText(/No verified badges are in this ruleset/)).toBeInTheDocument();
    expect(screen.getByText(/No verified animations are in this ruleset/)).toBeInTheDocument();
    expect(screen.getByText(/No verified Takeovers are in this ruleset/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate builds" })).toBeDisabled();
  });

  it("locks a preferred height only after the box is checked", async () => {
    installApi({ metadata: metadata({ attributes: fixtureAttributes }) });
    const user = userEvent.setup();
    renderAt("/build");
    const height = await screen.findByLabelText("Height (inches)");
    await user.type(height, "76");
    expect(screen.getByText("Preferred. The search may choose another value.")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Lock height (inches)" }));
    expect(screen.getByText("Locked.")).toBeInTheDocument();
    await user.clear(height);
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "Lock height (inches)" })).not.toBeChecked();
    });
    expect(screen.queryByText("Enter a height before locking it.")).not.toBeInTheDocument();
  });

  it("rejects a reserve that exceeds the available pools", async () => {
    installApi({ metadata: metadata({ attributes: fixtureAttributes }) });
    const user = userEvent.setup();
    renderAt("/build");
    const reserve = await screen.findByLabelText("Reserve count");
    await user.clear(reserve);
    await user.type(reserve, "4");
    expect(
      (await screen.findAllByText("Reserved Cap Breakers cannot exceed the total available.")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Generate builds" })).toBeDisabled();
  });

  it("sends a search and shows the unsupported result from the guarded API", async () => {
    const calls = installApi({
      metadata: metadata({ attributes: fixtureAttributes }),
      optimize: response("unsupported"),
    });
    const user = userEvent.setup();
    renderAt("/build");
    await addShot(user);
    const generate = screen.getByRole("button", { name: "Generate builds" });
    await waitFor(() => expect(generate).toBeEnabled());
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Rules check" })).toBeInTheDocument();
      expect(screen.getByText(/in-game legality was not judged/i)).toBeInTheDocument();
    });
    await user.click(generate);
    expect(await screen.findByRole("heading", { name: "Unsupported request" })).toBeInTheDocument();
    expect(screen.getByText("attribute_costs")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Proven infeasible" })).not.toBeInTheDocument();
    const optimize = calls.find((call) => call.url.endsWith("/api/v1/optimize"));
    expect(optimize?.body).toMatchObject({
      mode: "generate",
      attribute_targets: [{ id: "fixture_shot", target: 80, importance: "normal" }],
      playstyle: "automatic",
    });
  });

  it("refines from a result without turning every reference rating into a target", async () => {
    installApi({
      metadata: metadata({ attributes: fixtureAttributes }),
      optimize: response("partial_feasible", [recommendation("alpha", 84)]),
    });
    const user = userEvent.setup();
    renderAt("/build");
    await addShot(user);
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate builds" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Generate builds" }));
    expect(await screen.findByRole("heading", { name: "Partial result" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Proven ranking" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refine this build" }));
    expect(await screen.findByRole("heading", { name: "Refine" })).toBeInTheDocument();
    expect(screen.getByText("Fixture handle: 70")).toBeInTheDocument();
    expect(screen.getByLabelText("Target for Fixture shot")).toHaveValue("80");
    expect(screen.queryByLabelText("Target for Fixture handle")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Position")).toHaveValue("PG");
    expect(screen.getByRole("checkbox", { name: "Lock position" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Leave refine" }));
    expect(screen.queryByRole("heading", { name: "Refine" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Lock position" })).not.toBeChecked();
  });
});

describe("results and compare", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("explains a missing search", async () => {
    installApi({ metadata: metadata() });
    renderAt("/results");
    expect(await screen.findByText("There is no search to show.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the builder" })).toBeInTheDocument();
  });

  it("keeps infeasible, timeout, and proven results distinct", async () => {
    const cases: { status: OptimizeResponse["status"]; heading: string }[] = [
      { status: "infeasible_proven", heading: "Proven infeasible" },
      { status: "no_feasible_found_in_budget", heading: "No valid result found yet" },
      { status: "complete_proven", heading: "Proven ranking" },
    ];
    for (const item of cases) {
      installApi({
        metadata: metadata({ attributes: fixtureAttributes }),
        optimize: response(item.status, item.status === "complete_proven" ? [recommendation("alpha", 84)] : []),
      });
      const user = userEvent.setup();
      const view = renderAt("/build");
      await addShot(user);
      await waitFor(() => expect(screen.getByRole("button", { name: "Generate builds" })).toBeEnabled());
      await user.click(screen.getByRole("button", { name: "Generate builds" }));
      expect(await screen.findByRole("heading", { name: item.heading })).toBeInTheDocument();
      view.unmount();
    }
    expect(screen.queryByText("Required 99 cannot be reached.")).not.toBeInTheDocument();
  });

  it("shows conflicts for a proven infeasible search and caps compare at three", async () => {
    const builds = ["alpha", "beta", "gamma", "delta"].map((id, index) => {
      const build = recommendation(id, 80 + index);
      build.rank = index + 1;
      build.name = `Fixture ${id}`;
      return build;
    });
    installApi({
      metadata: metadata({ attributes: fixtureAttributes }),
      optimize: response("infeasible_proven", builds),
    });
    const user = userEvent.setup();
    renderAt("/build");
    await addShot(user);
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate builds" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Generate builds" }));
    expect(await screen.findByRole("heading", { name: "Proven infeasible" })).toBeInTheDocument();
    expect(screen.getByText("Required 99 cannot be reached.")).toBeInTheDocument();
    expect(screen.getByText("Requested 99. Achieved 95.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Closest legal options" })).toBeInTheDocument();
    for (const id of ["alpha", "beta", "gamma"]) {
      await user.click(screen.getByRole("checkbox", { name: `Compare Fixture ${id}` }));
    }
    expect(screen.getByText("Three builds are selected. Remove one to add another.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Compare Fixture delta" })).toBeDisabled();
    await user.click(screen.getByRole("link", { name: "Open compare" }));
    expect(await screen.findByRole("heading", { name: "Compare" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Fixture alpha" })).toBeInTheDocument();
    expect(screen.getAllByText(/81/).length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".bg-amber-50").length).toBeGreaterThan(0);
  });
});
