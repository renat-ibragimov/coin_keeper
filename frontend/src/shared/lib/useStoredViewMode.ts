import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { useAuth } from '@/features/auth/useAuth';
import { fetchBootstrap } from '@/features/dashboard/api';
import { updateSettings } from '@/features/settings/api';

export type ViewMode = 'cards' | 'table';
type ViewModeSettingsField = 'catalogViewMode' | 'collectionViewMode';

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
 * Remembers which view (cards or table) the viewer last picked for a page.
 *
 * `user_settings.{catalog,collection}_view_mode` (docs/api.md) is
 * the value that survives a new browser or device; localStorage is only a
 * fast local cache so a returning visit doesn't wait on the network before
 * picking a default. The URL stays authoritative over both: an explicit
 * `?view=` always wins, storage/server only supply the default when the URL
 * doesn't say, and every explicit switch is written to both.
 */
export function useStoredViewMode(storageKey: string, settingsField: ViewModeSettingsField) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  // Shares the cache with every other `['bootstrap']` query in the app — this
  // never fires an extra network request on its own.
  const bootstrapQuery = useQuery({
    queryKey: ['bootstrap'],
    queryFn: fetchBootstrap,
    enabled: Boolean(user),
  });
  const mutation = useMutation({
    mutationFn: (view: ViewMode) =>
      settingsField === 'catalogViewMode'
        ? updateSettings({ catalogViewMode: view })
        : updateSettings({ collectionViewMode: view }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['bootstrap'] }),
  });

  const resolve = useCallback(
    (urlView: string | undefined): ViewMode => {
      if (isViewMode(urlView)) return urlView;
      const serverView = bootstrapQuery.data?.settings[settingsField];
      if (isViewMode(serverView)) return serverView;
      return readStoredView(storageKey) ?? 'cards';
    },
    [storageKey, settingsField, bootstrapQuery.data],
  );

  const remember = useCallback(
    (view: ViewMode) => {
      try {
        localStorage.setItem(storageKey, view);
      } catch {
        /* remembering locally is a convenience, not a requirement */
      }
      if (user) mutation.mutate(view);
    },
    [storageKey, mutation, user],
  );

  return { resolve, remember };
}
