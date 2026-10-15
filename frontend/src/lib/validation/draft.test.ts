import { describe, expect, it } from "vitest";

import { emptyEditable, inspectDraft, type Catalog } from "./draft.ts";

const catalog: Catalog = {
  attributes: [
    { id: "fixture_shot", label: "Fixture shot", category: "fixture_shooting" },
    { id: "fixture_handle", label: "Fixture handle", category: "fixture_play" },
  ],
  badges: [],
  animations: [],
  takeovers: [],
  positions: ["PG", "SG", "SF", "PF", "C"],
  buildTypes: ["male", "female"],
  importanceLevels: ["required", "prioritized", "normal"],
  badgeTiers: ["bronze", "silver", "gold", "hall_of_fame"],
  playstyleIds: ["automatic"],
  categories: ["fixture_shooting", "fixture_play"],
};

function readyDraft() {
  const draft = emptyEditable();
  draft.targets = [{ id: "fixture_shot", target: "80", importance: "normal" }];
  return draft;
}

describe("inspectDraft", () => {
  it("keeps an unlocked measurement as a preference", () => {
    const draft = readyDraft();
    draft.height = "76";
    draft.heightLocked = false;
    const inspected = inspectDraft(draft, "generate", null, catalog);
    expect(inspected.request?.body?.height_in).toEqual({ value: 76, locked: false });
    expect(inspected.request?.reference).toBeUndefined();
  });

  it("rejects a reserve that is larger than the pools", () => {
    const draft = readyDraft();
    draft.reservedTotal = "4";
    const inspected = inspectDraft(draft, "generate", null, catalog);
    expect(inspected.request).toBeNull();
    expect(inspected.issues.map((issue) => issue.message)).toContain(
      "Reserved Cap Breakers cannot exceed the total available.",
    );
  });

  it("names a specialization pool from its category", () => {
    const draft = readyDraft();
    draft.specializationPools = [{ key: "pool-1", category: "fixture_shooting", available: "2" }];
    const inspected = inspectDraft(draft, "generate", null, catalog);
    expect(inspected.request?.cap_breakers?.pools).toEqual([
      {
        id: "spec_fixture_shooting",
        kind: "specialization",
        category: "fixture_shooting",
        available: 2,
      },
    ]);
  });

  it("requires a reference build in refine mode", () => {
    const inspected = inspectDraft(readyDraft(), "refine", null, catalog);
    expect(inspected.request).toBeNull();
    expect(inspected.issues.map((issue) => issue.message)).toContain(
      "Refine starts from a generated build.",
    );
  });
});
