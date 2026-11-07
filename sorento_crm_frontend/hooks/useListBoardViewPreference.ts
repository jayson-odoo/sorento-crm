'use client';

import { useCallback, useEffect, useState } from 'react';
import { localStore } from '@/lib/storage';

export type ListBoardViewMode = 'list' | 'board';

const PREFIX = 'icp:list-board-view:';

export function useListBoardViewPreference(storageKey: string, defaultMode: ListBoardViewMode = 'list') {
  const [mode, setModeState] = useState<ListBoardViewMode>(defaultMode);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStore.getItem(PREFIX + storageKey);
      if (raw === 'list' || raw === 'board') setModeState(raw);
    } catch {
      /* ignore */
    }
    setHydrated(true);
  }, [storageKey]);

  const setMode = useCallback(
    (next: ListBoardViewMode) => {
      setModeState(next);
      try {
        localStore.setItem(PREFIX + storageKey, next);
      } catch {
        /* ignore */
      }
    },
    [storageKey],
  );

  return { mode, setMode, hydrated };
}
