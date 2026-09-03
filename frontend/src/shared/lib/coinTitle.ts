/** The subset of a catalog record that carries its names. */
export interface TitledItem {
  titleUk: string | null;
  titleOriginal: string;
  titleEn: string | null;
  titleRu: string | null;
}

/**
 * Display title of a catalog item: the first filled of
 * titleUk → titleOriginal → titleEn → titleRu.
 *
 * The API already sends `title` computed by the same rule; the helper keeps
 * the rule in one place on the client for screens that compose the name
 * themselves (the card heading, the browser tab) and guards against a blank
 * string slipping through.
 */
export function coinTitle(item: TitledItem): string {
  const candidates = [item.titleUk, item.titleOriginal, item.titleEn, item.titleRu];
  for (const candidate of candidates) {
    if (candidate && candidate.trim()) return candidate.trim();
  }
  return item.titleOriginal;
}
