const CHOICE_LABELS: Record<string, string> = {
  required: "Required",
  prioritized: "Prioritized",
  normal: "Normal",
  bronze: "Bronze",
  silver: "Silver",
  gold: "Gold",
  hall_of_fame: "Hall of Fame",
  male: "Male",
  female: "Female",
  automatic: "Automatic",
  balanced: "Balanced",
  shooting: "Shooting",
  slashing: "Slashing",
  playmaking: "Playmaking",
  defense: "Defense",
  inside_rebounding: "Inside / rebounding",
};

export function choiceLabel(id: string): string {
  return CHOICE_LABELS[id] ?? id;
}

export function formatInches(inches: number): string {
  const feet = Math.floor(inches / 12);
  const rest = inches % 12;
  return `${inches} in (${feet}'${rest}")`;
}

export function formatWeight(pounds: number): string {
  return `${pounds} lb`;
}

export function formatElapsed(elapsedMs: number): string {
  if (elapsedMs < 1000) {
    return `${elapsedMs} ms`;
  }
  return `${(elapsedMs / 1000).toFixed(1)} seconds`;
}

export function formatScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}
