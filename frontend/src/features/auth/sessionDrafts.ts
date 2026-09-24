// Drafts never leave this tab's memory and never cross account boundaries.
let owner: number | null = null;
let retaining = false;
const recoverable = new Set<string>();
const drafts = new Map<string, unknown>();

export function setDraftOwner(id: number | null): void {
  if (owner !== id || id === null) {
    drafts.clear();
    recoverable.clear();
  }
  owner = id;
  retaining = false;
}

export function retainSessionDrafts(): void {
  retaining = true;
  for (const key of drafts.keys()) recoverable.add(key);
}
export function readSessionDraft<T>(key: string): T | undefined {
  return recoverable.has(key) ? (drafts.get(key) as T | undefined) : undefined;
}
export function writeSessionDraft(key: string, value: unknown): void {
  if (owner !== null) drafts.set(key, value);
  recoverable.delete(key);
}
export function releaseSessionDraft(key: string): void {
  if (!retaining) {
    drafts.delete(key);
    recoverable.delete(key);
  }
}
