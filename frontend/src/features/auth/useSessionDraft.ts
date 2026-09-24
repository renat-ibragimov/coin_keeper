import { useEffect, useState } from 'react';
import { readSessionDraft, releaseSessionDraft, writeSessionDraft } from './sessionDrafts';

/** Keep active form input through reauthentication, not through ordinary navigation. */
export function useSessionDraft<T>(key: string, initial: T | (() => T)) {
  const [value, setValue] = useState<T>(
    () =>
      readSessionDraft<T>(key) ??
      (typeof initial === 'function' ? (initial as () => T)() : initial),
  );
  useEffect(() => {
    writeSessionDraft(key, value);
  }, [key, value]);
  useEffect(() => () => releaseSessionDraft(key), [key]);
  return [value, setValue] as const;
}
