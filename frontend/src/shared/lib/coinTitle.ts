/** The subset of a catalog record that carries its names. */
export interface TitledItem {
  titleOriginal: string;
  titleUk: string | null;
  titleEn: string | null;
}

/**
 * Display title of a catalog item: `title_{locale}` and then the original.
 *
 * The original is the issuer's own wording and is never translated, so it is
 * the only fallback there is — there is no Russian slot behind it
 * (docs/04-business-rules.md). The API already sends `title` computed by the
 * same rule; the helper keeps the rule in one place on the client for screens
 * that compose the name themselves (the card heading, the browser tab).
 */
export function coinTitle(item: TitledItem, locale: string): string {
  const translated = locale.startsWith('en') ? item.titleEn : item.titleUk;
  if (translated && translated.trim()) return translated.trim();
  return item.titleOriginal.trim();
}

/** Whether the original wording is worth showing next to the displayed name. */
export function showsOriginal(item: TitledItem, locale: string): boolean {
  return coinTitle(item, locale) !== item.titleOriginal.trim();
}
