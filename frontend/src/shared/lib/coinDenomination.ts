/** The subset of a catalog record that says what the coin is worth. */
export interface DenominatedItem {
  denomination: { label: string } | null;
  denominationText: string | null;
}

/**
 * The coin's face value: the denominations dictionary label ("2 гривні")
 * first, then the free text kept on a record the dictionary does not cover.
 *
 * The same shape as `coinMaterial`, and for the same reason — the dictionary
 * is seeded from what the catalogue actually holds, so for most issuers it
 * says nothing and the collector's own words are all there is
 * (docs/business-rules.md, §14).
 */
export function coinDenomination(item: DenominatedItem): string | null {
  const label = item.denomination?.label.trim();
  if (label) return label;
  const text = item.denominationText?.trim();
  return text ? text : null;
}
