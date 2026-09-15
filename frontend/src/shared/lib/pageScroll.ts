/**
 * Where the page scrolls depends on the layout.
 *
 * On the desktop shell the document itself does not scroll: the header is a
 * fixed row and everything below it scrolls inside the shell's own scroll
 * area, so the scrollbar never runs past the header and its reserved gutter
 * sits on the page ground, where it is invisible until there is something to
 * scroll (docs/08-ui-map.md). On the phone layout the document scrolls as
 * usual — an inner scroller would stop the browser's URL bar from collapsing.
 *
 * Both helpers below address whichever of the two is live, so callers never
 * have to ask.
 */

const SCROLL_AREA = '[data-scroll-area]';

function scrollArea(): HTMLElement | null {
  return document.querySelector<HTMLElement>(SCROLL_AREA);
}

/** Puts the page back at the top: a new route, a new page of results. */
export function scrollPageToTop(): void {
  scrollArea()?.scrollTo({ top: 0 });
  window.scrollTo(0, 0);
}

/**
 * Freezes the page behind an overlay. Returns the undo, so a caller can hand
 * it straight back from an effect. Nesting is safe — each lock restores the
 * value it found, and the outer one still reads `hidden`.
 */
export function lockPageScroll(): () => void {
  const targets = [document.body, scrollArea()].filter((el): el is HTMLElement => el !== null);
  const previous = targets.map((el) => el.style.overflow);
  targets.forEach((el) => {
    el.style.overflow = 'hidden';
  });
  return () => {
    targets.forEach((el, index) => {
      el.style.overflow = previous[index] ?? '';
    });
  };
}
