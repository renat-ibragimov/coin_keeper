/** Page numbers with ellipses: 1 … around current … last. */
export function pageItems(page: number, pageCount: number): (number | 'gap')[] {
  const pages = new Set<number>([1, pageCount, page - 1, page, page + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= pageCount).sort((a, b) => a - b);
  const items: (number | 'gap')[] = [];
  let previous = 0;
  for (const p of sorted) {
    if (previous && p - previous > 1) items.push('gap');
    items.push(p);
    previous = p;
  }
  return items;
}
