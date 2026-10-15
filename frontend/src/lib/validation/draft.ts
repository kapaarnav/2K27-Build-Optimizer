import { z } from "zod";

import type { MetadataResponse, OptimizeRequest, RefineReference } from "../api/client.ts";
import type { components } from "../api/schema.ts";

type Importance = components["schemas"]["Importance"];
type BadgeTier = components["schemas"]["BadgeTier"];
type Position = components["schemas"]["Position"];
type BuildType = components["schemas"]["BuildType"];

export const RATING_MIN = 0;
export const RATING_MAX = 150;
export const INCH_MIN = 1;
export const INCH_MAX = 150;
export const POUND_MIN = 1;
export const POUND_MAX = 1000;
export const POOL_MAX = 100;

const IDENTIFIER = /^[a-z][a-z0-9_]{0,63}$/;

export type CatalogEntry = { id: string; label: string };

export type Catalog = {
  attributes: { id: string; label: string; category: string }[];
  badges: CatalogEntry[];
  animations: CatalogEntry[];
  takeovers: CatalogEntry[];
  positions: readonly string[];
  buildTypes: readonly string[];
  importanceLevels: readonly string[];
  badgeTiers: readonly string[];
  playstyleIds: readonly string[];
  categories: string[];
};

const editableObject = z.object({
  buildType: z.string(),
  buildTypeLocked: z.boolean(),
  position: z.string(),
  positionLocked: z.boolean(),
  height: z.string(),
  heightLocked: z.boolean(),
  weight: z.string(),
  weightLocked: z.boolean(),
  wingspan: z.string(),
  wingspanLocked: z.boolean(),
  targets: z.array(
    z.object({
      id: z.string(),
      target: z.string(),
      importance: z.string(),
    }),
  ),
  unrestrictedAvailable: z.string(),
  specializationPools: z.array(
    z.object({
      key: z.string(),
      category: z.string(),
      available: z.string(),
    }),
  ),
  reservedTotal: z.string(),
  forbiddenAttributeIds: z.array(z.string()),
  minimumAllocations: z.array(
    z.object({
      attributeId: z.string(),
      count: z.string(),
    }),
  ),
  badges: z.array(
    z.object({
      id: z.string(),
      minimumTier: z.string(),
      importance: z.string(),
    }),
  ),
  animations: z.array(
    z.object({
      id: z.string(),
      importance: z.string(),
    }),
  ),
  takeovers: z.array(
    z.object({
      id: z.string(),
      importance: z.string(),
    }),
  ),
  playstyle: z.string(),
});

export type EditableDraft = z.infer<typeof editableObject>;
export type DraftSchema = ReturnType<typeof createDraftSchema>;

export type DraftIssue = {
  field: string;
  message: string;
};

export function coerceEditable(value: unknown): EditableDraft {
  const source = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const base = emptyEditable();
  return {
    buildType: text(source.buildType, base.buildType),
    buildTypeLocked: flag(source.buildTypeLocked, base.buildTypeLocked),
    position: text(source.position, base.position),
    positionLocked: flag(source.positionLocked, base.positionLocked),
    height: text(source.height, base.height),
    heightLocked: flag(source.heightLocked, base.heightLocked),
    weight: text(source.weight, base.weight),
    weightLocked: flag(source.weightLocked, base.weightLocked),
    wingspan: text(source.wingspan, base.wingspan),
    wingspanLocked: flag(source.wingspanLocked, base.wingspanLocked),
    targets: rows(source.targets, (item) => {
      const id = text(item.id, "");
      if (!id) {
        return null;
      }
      return {
        id,
        target: text(item.target, ""),
        importance: text(item.importance, "normal"),
      };
    }),
    unrestrictedAvailable: text(source.unrestrictedAvailable, base.unrestrictedAvailable),
    specializationPools: rows(source.specializationPools, (item) => {
      const key = text(item.key, "");
      const category = text(item.category, "");
      if (!key || !category) {
        return null;
      }
      return { key, category, available: text(item.available, "") };
    }),
    reservedTotal: text(source.reservedTotal, base.reservedTotal),
    forbiddenAttributeIds: Array.isArray(source.forbiddenAttributeIds)
      ? source.forbiddenAttributeIds.filter((item): item is string => typeof item === "string")
      : [],
    minimumAllocations: rows(source.minimumAllocations, (item) => {
      const attributeId = text(item.attributeId, "");
      if (!attributeId) {
        return null;
      }
      return { attributeId, count: text(item.count, "") };
    }),
    badges: rows(source.badges, (item) => {
      const id = text(item.id, "");
      if (!id) {
        return null;
      }
      return {
        id,
        minimumTier: text(item.minimumTier, "bronze"),
        importance: text(item.importance, "normal"),
      };
    }),
    animations: rows(source.animations, (item) => unlockRow(item)),
    takeovers: rows(source.takeovers, (item) => unlockRow(item)),
    playstyle: text(source.playstyle, base.playstyle),
  };
}

function text(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function flag(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function rows<T>(value: unknown, map: (item: Record<string, unknown>) => T | null): T[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const mapped = map(item as Record<string, unknown>);
    return mapped ? [mapped] : [];
  });
}

function unlockRow(item: Record<string, unknown>): EditableDraft["animations"][number] | null {
  const id = text(item.id, "");
  if (!id) {
    return null;
  }
  return { id, importance: text(item.importance, "normal") };
}

export function emptyEditable(): EditableDraft {
  return {
    buildType: "",
    buildTypeLocked: false,
    position: "",
    positionLocked: false,
    height: "",
    heightLocked: false,
    weight: "",
    weightLocked: false,
    wingspan: "",
    wingspanLocked: false,
    targets: [],
    unrestrictedAvailable: "",
    specializationPools: [],
    reservedTotal: "0",
    forbiddenAttributeIds: [],
    minimumAllocations: [],
    badges: [],
    animations: [],
    takeovers: [],
    playstyle: "automatic",
  };
}

export function catalogFrom(metadata: MetadataResponse): Catalog {
  const categories: string[] = [];
  for (const attribute of metadata.attributes) {
    if (!IDENTIFIER.test(attribute.category) || categories.includes(attribute.category)) {
      continue;
    }
    categories.push(attribute.category);
  }
  return {
    attributes: metadata.attributes,
    badges: metadata.badges,
    animations: metadata.animations,
    takeovers: metadata.takeovers,
    positions: metadata.positions,
    buildTypes: metadata.build_types,
    importanceLevels: metadata.importance_levels,
    badgeTiers: metadata.badge_tiers,
    playstyleIds: metadata.playstyles.map((item) => item.id),
    categories,
  };
}

export function createDraftSchema(catalog: Catalog) {
  return editableObject.superRefine((draft, ctx) => {
    checkChoice(ctx, "buildType", draft.buildType, draft.buildTypeLocked, catalog.buildTypes, "build type");
    checkChoice(ctx, "position", draft.position, draft.positionLocked, catalog.positions, "position");
    checkMeasurement(ctx, "height", draft.height, draft.heightLocked, INCH_MIN, INCH_MAX, "Height");
    checkMeasurement(ctx, "weight", draft.weight, draft.weightLocked, POUND_MIN, POUND_MAX, "Weight");
    checkMeasurement(
      ctx,
      "wingspan",
      draft.wingspan,
      draft.wingspanLocked,
      INCH_MIN,
      INCH_MAX,
      "Wingspan",
    );
    checkTargets(ctx, draft, catalog);
    const pools = checkPools(ctx, draft, catalog);
    checkMinimums(ctx, draft, catalog, pools);
    checkUnlocks(ctx, draft.badges, catalog.badges, catalog, "badges", "badge", true);
    checkUnlocks(ctx, draft.animations, catalog.animations, catalog, "animations", "animation", false);
    checkUnlocks(ctx, draft.takeovers, catalog.takeovers, catalog, "takeovers", "Takeover", false);
    if (!catalog.playstyleIds.includes(draft.playstyle)) {
      add(ctx, "playstyle", "Choose a playstyle from the list.");
    }
  });
}

export function inspectDraft(
  editable: EditableDraft,
  mode: "generate" | "refine",
  reference: RefineReference | null,
  catalog: Catalog,
): { issues: DraftIssue[]; request: OptimizeRequest | null } {
  const parsed = createDraftSchema(catalog).safeParse(editable);
  const issues = parsed.success ? [] : issuesFrom(parsed.error.issues);
  if (mode === "refine" && reference === null) {
    issues.push({
      field: "reference",
      message: "Refine starts from a generated build.",
    });
  }
  if (!parsed.success || issues.length > 0) {
    return { issues, request: null };
  }
  return { issues: [], request: toRequest(parsed.data, mode, reference) };
}

export function attributeLabel(catalog: Catalog, id: string): string {
  return catalog.attributes.find((item) => item.id === id)?.label ?? id;
}

function toRequest(
  draft: EditableDraft,
  mode: "generate" | "refine",
  reference: RefineReference | null,
): OptimizeRequest {
  const used = new Set<string>();
  const pools: NonNullable<OptimizeRequest["cap_breakers"]>["pools"] = [];
  const unrestricted = Number(draft.unrestrictedAvailable.trim() || "0");
  if (unrestricted > 0) {
    pools.push({ id: "unrestricted", kind: "unrestricted", available: unrestricted });
    used.add("unrestricted");
  }
  for (const pool of draft.specializationPools) {
    const id = nextPoolId(pool.category, used);
    pools.push({
      id,
      kind: "specialization",
      category: pool.category,
      available: Number(pool.available),
    });
  }
  const request: OptimizeRequest = {
    mode,
    body: {
      build_type: {
        value: draft.buildType === "" ? null : (draft.buildType as BuildType),
        locked: draft.buildType !== "" && draft.buildTypeLocked,
      },
      position: {
        value: draft.position === "" ? null : (draft.position as Position),
        locked: draft.position !== "" && draft.positionLocked,
      },
      height_in: lockedNumber(draft.height, draft.heightLocked),
      weight_lb: lockedNumber(draft.weight, draft.weightLocked),
      wingspan_in: lockedNumber(draft.wingspan, draft.wingspanLocked),
    },
    attribute_targets: draft.targets.map((target) => ({
      id: target.id,
      target: Number(target.target),
      importance: target.importance as Importance,
    })),
    cap_breakers: {
      pools,
      reserved_total: Number(draft.reservedTotal.trim() || "0"),
      forbidden_attribute_ids: draft.forbiddenAttributeIds,
      minimum_allocations: draft.minimumAllocations.map((item) => ({
        attribute_id: item.attributeId,
        count: Number(item.count),
      })),
    },
    badges: draft.badges.map((badge) => ({
      id: badge.id,
      minimum_tier: badge.minimumTier as BadgeTier,
      importance: badge.importance as Importance,
    })),
    animations: draft.animations.map((item) => ({
      id: item.id,
      importance: item.importance as Importance,
    })),
    takeovers: draft.takeovers.map((item) => ({
      id: item.id,
      importance: item.importance as Importance,
    })),
    playstyle: draft.playstyle,
  };
  if (mode === "refine" && reference) {
    request.reference = reference;
  }
  return request;
}

function lockedNumber(
  value: string,
  locked: boolean,
): { value: number | null; locked: boolean } {
  const trimmed = value.trim();
  if (trimmed === "") {
    return { value: null, locked: false };
  }
  return { value: Number(trimmed), locked };
}

function nextPoolId(category: string, used: Set<string>): string {
  const slug = category.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  const base = slug && IDENTIFIER.test(slug) ? `spec_${slug}` : "spec_pool";
  let id = base.slice(0, 64);
  let suffix = 2;
  while (used.has(id)) {
    const tail = `_${suffix}`;
    id = `${base.slice(0, 64 - tail.length)}${tail}`;
    suffix += 1;
  }
  used.add(id);
  return id;
}

type IssueContext = z.RefinementCtx;

function add(ctx: IssueContext, field: string, message: string): void {
  ctx.addIssue({
    code: "custom",
    message,
    path: field.split(".").map((part) => (/^\d+$/.test(part) ? Number(part) : part)),
  });
}

function issuesFrom(issues: { path: PropertyKey[]; message: string }[]): DraftIssue[] {
  return issues.map((issue) => ({
    field: issue.path.map(String).join("."),
    message: issue.message,
  }));
}

function checkChoice(
  ctx: IssueContext,
  field: string,
  value: string,
  locked: boolean,
  allowed: readonly string[],
  label: string,
): void {
  if (value === "" && locked) {
    add(ctx, field, `Choose a ${label} before locking it.`);
    return;
  }
  if (value !== "" && !allowed.includes(value)) {
    add(ctx, field, `Choose a ${label} from the list.`);
  }
}

function checkMeasurement(
  ctx: IssueContext,
  field: string,
  value: string,
  locked: boolean,
  minimum: number,
  maximum: number,
  label: string,
): void {
  const parsed = parseWhole(value);
  if (parsed.kind === "empty") {
    if (locked) {
      add(ctx, field, `Enter a ${label.toLowerCase()} before locking it.`);
    }
    return;
  }
  if (parsed.kind === "invalid") {
    add(ctx, field, `${label} has to be a whole number.`);
    return;
  }
  if (parsed.value < minimum || parsed.value > maximum) {
    add(
      ctx,
      field,
      `${label} has to be from ${minimum} to ${maximum}. That ceiling is the API limit, not a verified in-game range.`,
    );
  }
}

function checkTargets(ctx: IssueContext, draft: EditableDraft, catalog: Catalog): void {
  if (draft.targets.length === 0) {
    const message =
      catalog.attributes.length === 0
        ? "Add at least one attribute target after a verified catalog is loaded."
        : "Add at least one attribute target.";
    add(ctx, "targets", message);
    return;
  }
  const seen = new Set<string>();
  draft.targets.forEach((target, index) => {
    if (!catalog.attributes.some((item) => item.id === target.id)) {
      add(ctx, `targets.${index}.id`, "Choose an attribute from the verified catalog.");
    }
    if (seen.has(target.id)) {
      add(ctx, `targets.${index}.id`, "Each attribute can be targeted once.");
    }
    seen.add(target.id);
    const parsed = parseWhole(target.target);
    if (parsed.kind === "empty") {
      add(ctx, `targets.${index}.target`, "Enter a target rating.");
    } else if (parsed.kind === "invalid") {
      add(ctx, `targets.${index}.target`, "A target rating has to be a whole number.");
    } else if (parsed.value < RATING_MIN || parsed.value > RATING_MAX) {
      add(
        ctx,
        `targets.${index}.target`,
        `A target rating has to be from ${RATING_MIN} to ${RATING_MAX}. That ceiling is the API limit, not a verified in-game range.`,
      );
    }
    if (!catalog.importanceLevels.includes(target.importance)) {
      add(ctx, `targets.${index}.importance`, "Choose an importance from the list.");
    }
  });
}

function checkPools(ctx: IssueContext, draft: EditableDraft, catalog: Catalog): number {
  let total = 0;
  const unrestricted = parseWhole(draft.unrestrictedAvailable);
  if (unrestricted.kind === "invalid") {
    add(ctx, "unrestrictedAvailable", "Unrestricted Cap Breakers have to be a whole number.");
  } else if (unrestricted.kind === "number") {
    if (unrestricted.value > POOL_MAX) {
      add(ctx, "unrestrictedAvailable", `Unrestricted Cap Breakers have to be from 0 to ${POOL_MAX}.`);
    } else {
      total += unrestricted.value;
    }
  }
  const seenCategories = new Set<string>();
  draft.specializationPools.forEach((pool, index) => {
    if (!catalog.categories.includes(pool.category)) {
      add(ctx, `specializationPools.${index}.category`, "Choose a verified attribute category.");
    }
    if (seenCategories.has(pool.category)) {
      add(ctx, `specializationPools.${index}.category`, "Each specialization category can be used once.");
    }
    seenCategories.add(pool.category);
    const available = parseWhole(pool.available);
    if (available.kind !== "number" || available.value < 1 || available.value > POOL_MAX) {
      add(
        ctx,
        `specializationPools.${index}.available`,
        `Enter a specialization count from 1 to ${POOL_MAX}.`,
      );
    } else {
      total += available.value;
    }
  });
  const reserved = parseWhole(draft.reservedTotal);
  if (reserved.kind === "empty") {
    add(ctx, "reservedTotal", "Enter a reserve count, or 0 to keep the full pool.");
  } else if (reserved.kind === "invalid" || reserved.value > POOL_MAX) {
    add(ctx, "reservedTotal", `Reserve has to be a whole number from 0 to ${POOL_MAX}.`);
  } else if (reserved.value > total) {
    add(ctx, "reservedTotal", "Reserved Cap Breakers cannot exceed the total available.");
  }
  const forbidden = new Set<string>();
  draft.forbiddenAttributeIds.forEach((id, index) => {
    if (!catalog.attributes.some((item) => item.id === id)) {
      add(ctx, `forbiddenAttributeIds.${index}`, "Forbidden attributes come from the verified catalog.");
    }
    if (forbidden.has(id)) {
      add(ctx, `forbiddenAttributeIds.${index}`, "Each forbidden attribute can be listed once.");
    }
    forbidden.add(id);
  });
  return total;
}

function checkMinimums(
  ctx: IssueContext,
  draft: EditableDraft,
  catalog: Catalog,
  poolTotal: number,
): void {
  const reserved = parseWhole(draft.reservedTotal);
  const spendable = reserved.kind === "number" ? poolTotal - reserved.value : poolTotal;
  let requested = 0;
  const seen = new Set<string>();
  draft.minimumAllocations.forEach((item, index) => {
    if (!catalog.attributes.some((attribute) => attribute.id === item.attributeId)) {
      add(ctx, `minimumAllocations.${index}.attributeId`, "Choose an attribute from the verified catalog.");
    }
    if (seen.has(item.attributeId)) {
      add(ctx, `minimumAllocations.${index}.attributeId`, "Each attribute can have one minimum allocation.");
    }
    seen.add(item.attributeId);
    const count = parseWhole(item.count);
    if (count.kind !== "number" || count.value > POOL_MAX) {
      add(ctx, `minimumAllocations.${index}.count`, `Enter a minimum from 0 to ${POOL_MAX}.`);
      return;
    }
    requested += count.value;
  });
  if (requested > spendable) {
    add(ctx, "minimumAllocations", "Minimum Cap Breaker allocations exceed the spendable total.");
  }
}

function checkUnlocks(
  ctx: IssueContext,
  rows: { id: string; importance: string; minimumTier?: string }[],
  allowed: CatalogEntry[],
  catalog: Catalog,
  field: string,
  label: string,
  hasTier: boolean,
): void {
  const seen = new Set<string>();
  rows.forEach((row, index) => {
    if (!allowed.some((item) => item.id === row.id)) {
      add(ctx, `${field}.${index}.id`, `Choose a ${label} from the verified catalog.`);
    }
    if (seen.has(row.id)) {
      add(ctx, `${field}.${index}.id`, `Each ${label} can be requested once.`);
    }
    seen.add(row.id);
    if (!catalog.importanceLevels.includes(row.importance)) {
      add(ctx, `${field}.${index}.importance`, "Choose an importance from the list.");
    }
    if (hasTier && row.minimumTier && !catalog.badgeTiers.includes(row.minimumTier)) {
      add(ctx, `${field}.${index}.minimumTier`, "Choose a badge tier from the list.");
    }
  });
}

type ParsedWhole =
  | { kind: "empty" }
  | { kind: "invalid" }
  | { kind: "number"; value: number };

function parseWhole(value: string): ParsedWhole {
  const trimmed = value.trim();
  if (trimmed === "") {
    return { kind: "empty" };
  }
  if (!/^\d+$/.test(trimmed)) {
    return { kind: "invalid" };
  }
  return { kind: "number", value: Number(trimmed) };
}
