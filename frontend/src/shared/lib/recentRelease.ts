const DAY_MS = 24 * 60 * 60 * 1000;

/** True only for a known release date in the last 30 calendar days. */
export function isRecentRelease(issueDate: string | null | undefined, now = new Date()): boolean {
  if (!issueDate) return false;
  const release = Date.parse(`${issueDate}T00:00:00Z`);
  if (!Number.isFinite(release)) return false;
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const age = today - release;
  return age >= 0 && age <= 30 * DAY_MS;
}
