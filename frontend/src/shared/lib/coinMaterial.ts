/** The subset of a catalog record that says what the coin is made of. */
export interface MaterialedItem {
  composition: { name: string } | null;
  material: string | null;
}

/**
 * What the coin is made of, for a listing: the composition dictionary name
 * ("Нейзильбер") first, then the free-text material kept on records the
 * dictionary does not cover.
 *
 * Nothing at all when the record says nothing. The metal kind is a filter
 * facet, not a material, so a listing leaves the slot empty rather than
 * printing "Недорогоцінний" in the place of a material — only the coin page,
 * which labels the row, falls back to it (docs/08-ui-map.md).
 */
export function coinMaterial(item: MaterialedItem): string | null {
  const composition = item.composition?.name.trim();
  if (composition) return composition;
  const material = item.material?.trim();
  return material ? material : null;
}

/**
 * The same material shortened to sit beside the face value on a grid card:
 * the metal and no more.
 *
 * A full alloy description ("Мідь із марганцево-латунним покриттям") takes the
 * whole line and reads as the card's main fact, which it is not — the card
 * answers "what is it made of" at a glance, keeps the full text in its
 * tooltip, and leaves it to the table column and the coin page to spell out.
 * Two words, and a trailing short one goes too: "Сталь із…" says nothing more
 * than "Сталь…" and reads worse (owner, 2026-09-09). Measured in characters
 * rather than against a list of prepositions — the material is data, in
 * whatever language the issuer writes (docs/08-ui-map.md).
 */
const WORDS_ON_A_CARD = 2;
const SHORTEST_WORD_WORTH_KEEPING = 3;

export function shortMaterial(material: string): string {
  const words = material.split(/\s+/);
  const kept = words.slice(0, WORDS_ON_A_CARD);
  if (kept.length > 1 && kept[kept.length - 1]!.length < SHORTEST_WORD_WORTH_KEEPING) kept.pop();
  if (kept.length === words.length) return material;
  return `${kept.join(' ')}…`;
}
