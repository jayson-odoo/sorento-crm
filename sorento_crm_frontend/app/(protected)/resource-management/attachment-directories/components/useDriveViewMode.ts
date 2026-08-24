'use client';

import { useCallback, useEffect, useState } from 'react';

export type DriveViewMode = 'list' | 'grid';

const STORAGE_KEY = 'resource-management.drive.view-mode';
const DEFAULT_MODE: DriveViewMode = 'list';

function readStored(): DriveViewMode {
  if (typeof window === 'undefined') return DEFAULT_MODE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw === 'grid' || raw === 'list' ? raw : DEFAULT_MODE;
  } catch {
    return DEFAULT_MODE;
  }
}

/**
 * View-mode (list | grid) for the Unified Drive, persisted per-user in
 * localStorage so the choice survives reloads (UAC A5). Default = list (D12).
 */
export function useDriveViewMode(): [DriveViewMode, (mode: DriveViewMode) => void] {
  // Start from the default on the server/first paint to avoid hydration mismatch,
  // then hydrate from storage on mount.
  const [mode, setMode] = useState<DriveViewMode>(DEFAULT_MODE);

  useEffect(() => {
    setMode(readStored());
  }, []);

  const persist = useCallback((next: DriveViewMode) => {
    setMode(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore - non-persistent fallback is acceptable
    }
  }, []);

  return [mode, persist];
}
