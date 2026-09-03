import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';
import { useLocation } from 'react-router-dom';

interface DismissableOptions {
  /** Elements that count as "inside": a pointer press anywhere else dismisses. Empty — no outside handling. */
  inside?: RefObject<HTMLElement | null>[];
  /** Escape dismisses (default true). */
  escape?: boolean;
  /** A navigation dismisses (default true). */
  routeChange?: boolean;
}

/**
 * The one rule for every popup, sheet, drawer and dropdown: it goes away on
 * Escape, on a press outside it (pointerdown, so a touch closes it before the
 * page underneath receives a click), and when the route changes. Choosing an
 * item is the caller's job — it navigates or closes explicitly.
 */
export function useDismissable(
  open: boolean,
  onDismiss: () => void,
  { inside = [], escape = true, routeChange = true }: DismissableOptions = {},
): void {
  const location = useLocation();
  const dismiss = useRef(onDismiss);
  dismiss.current = onDismiss;
  // The location at the moment of opening: only a later navigation counts.
  const openedAt = useRef(location.key);
  const insideRef = useRef(inside);
  insideRef.current = inside;

  useEffect(() => {
    if (open) openedAt.current = location.key;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- captured only when opening
  }, [open]);

  useEffect(() => {
    if (!open || !routeChange) return;
    if (location.key !== openedAt.current) dismiss.current();
  }, [open, routeChange, location.key]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (escape && event.key === 'Escape') dismiss.current();
    };
    const onPointer = (event: PointerEvent) => {
      const refs = insideRef.current;
      if (refs.length === 0) return;
      const target = event.target as Node | null;
      if (target && refs.some((ref) => ref.current?.contains(target))) return;
      dismiss.current();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [open, escape]);
}
