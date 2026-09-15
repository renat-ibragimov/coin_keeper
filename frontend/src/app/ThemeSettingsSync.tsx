import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { useAuth } from '@/features/auth/useAuth';
import { fetchBootstrap } from '@/features/dashboard/api';
import { useTheme } from '@/shared/theme/useTheme';

/**
 * Applies the server's stored theme once per login, without writing back to
 * it: `setPreference` only touches local state and localStorage, so this
 * cannot loop into another PATCH. A brand-new device or browser starts from
 * `readPreference()`'s guess (localStorage, then system) and upgrades to the
 * account's real value the moment `GET /bootstrap` answers — the same
 * "instant local guess, then reconcile" shape `ck-locale` already uses.
 *
 * Does not touch view mode: that's seeded once per page from
 * `useStoredViewMode`, and pushing a live value into an already-open
 * catalog/collection page would yank the view out from under whoever is
 * looking at it.
 */
export function ThemeSettingsSync() {
  const { user } = useAuth();
  const { setPreference } = useTheme();
  const appliedForUserId = useRef<number | null>(null);

  // Shares the cache with every other `['bootstrap']` query in the app —
  // this component alone never causes an extra network request.
  const query = useQuery({
    queryKey: ['bootstrap'],
    queryFn: fetchBootstrap,
    enabled: user != null,
  });

  useEffect(() => {
    const theme = query.data?.settings.theme;
    if (!user || !theme || appliedForUserId.current === user.id) return;
    appliedForUserId.current = user.id;
    if (theme === 'light' || theme === 'dark' || theme === 'system') setPreference(theme);
  }, [user, query.data, setPreference]);

  return null;
}
