/**
 * The name of a language in the reader's own language.
 *
 * `original_lang` can be any ISO 639-1 code the country seed carries, so the
 * names come from the browser's CLDR data rather than from a list we would
 * have to keep in step with it. The code itself is the fallback.
 */
export function languageName(code: string, locale: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: 'language' }).of(code) ?? code;
  } catch {
    return code;
  }
}
