import { useCallback } from 'react';

export type ViewMode = 'cards' | 'table';

function isViewMode(value: string | null | undefined): value is ViewMode {
  return value === 'cards' || value === 'table';
}

function readStoredView(key: string): ViewMode | undefined {
  try {
    const saved = localStorage.getItem(key);
    return isViewMode(saved) ? saved : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Remembers which view (cards or table) the viewer last picked for a page —
 * same localStorage pattern as ThemeProvider. The URL stays authoritative: an
 * explicit `?view=` always wins; storage only supplies the default when the
 * URL doesn't say, and every explicit switch is written back to it so the
 * choice survives the next visit.
 */
export function useStoredViewMode(storageKey: string) {
  const resolve = useCallback(
    (urlView: string | undefined): ViewMode => {
      if (isViewMode(urlView)) return urlView;
      return readStoredView(storageKey) ?? 'cards';
    },
    [storageKey],
  );

  const remember = useCallback(
    (view: ViewMode) => {
      try {
        localStorage.setItem(storageKey, view);
      } catch {
        /* remembering is a convenience, not a requirement */
      }
    },
    [storageKey],
  );

  return { resolve, remember };
}
