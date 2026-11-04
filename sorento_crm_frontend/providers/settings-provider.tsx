'use client';

/* eslint-disable @typescript-eslint/no-explicit-any */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { APP_SETTINGS } from '@/config/settings.config';
import { Settings } from '@/config/types';
import { localStore } from '@/lib/storage';

type Path = string;

type SettingsContextType = {
  getOption: <T = any>(path: Path) => T;
  setOption: <T = any>(path: Path, value: T) => void;
  storeOption: <T = any>(path: Path, value: T) => void;
  settings: Settings;
};

const SettingsContext = createContext<SettingsContextType | undefined>(
  undefined,
);

const LOCAL_STORAGE_PREFIX = 'app_settings_';

const isBrowser = () => typeof window !== 'undefined';

function getFromPath(obj: any, path: string): any {
  return path.split('.').reduce((acc, part) => acc?.[part], obj);
}

function setToPath(obj: any, path: string, value: any): Settings {
  const keys = path.split('.');
  const lastKey = keys.pop()!;
  const lastObj = keys.reduce((acc, key) => (acc[key] ??= {}), obj);
  lastObj[lastKey] = value;
  return { ...obj };
}

// Storage goes through lib/storage, which never throws (Safari with storage blocked).
function storeLeaf(path: string, value: unknown) {
  localStore.setItem(`${LOCAL_STORAGE_PREFIX}${path}`, JSON.stringify(value));
}

function getLeafFromStorage(path: string): any {
  const item = localStore.getItem(`${LOCAL_STORAGE_PREFIX}${path}`);
  if (!item) return undefined;
  try {
    return JSON.parse(item);
  } catch {
    return undefined;
  }
}

/**
 * A fresh copy of the defaults. Not `structuredClone`: Safari before 15.4 has none,
 * and a ReferenceError here took down every page, sign-in included, with "The app
 * could not start" (CLIENT-ERROR-REPORT). APP_SETTINGS is plain JSON data.
 */
function defaultSettings(): Settings {
  return JSON.parse(JSON.stringify(APP_SETTINGS)) as Settings;
}

/** Stored setting paths; none when storage is blocked (settings then live in memory). */
function storedPaths(): string[] {
  return localStore
    .keys()
    .filter((key) => key.startsWith(LOCAL_STORAGE_PREFIX))
    .map((key) => key.slice(LOCAL_STORAGE_PREFIX.length));
}

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [settings, setSettings] = useState<Settings>(defaultSettings);

  // Load settings from localStorage after mount
  useEffect(() => {
    if (!isBrowser()) return;

    const init = defaultSettings();
    storedPaths().forEach((path) => {
      const value = getLeafFromStorage(path);
      if (value !== undefined) {
        setToPath(init, path, value);
      }
    });
    setSettings(init);
  }, []); // Empty dependency array to run once on mount

  const getOption = useCallback(
    <T,>(path: string): T => {
      return getFromPath(settings, path) as T;
    },
    [settings],
  );

  const setOption = useCallback(<T,>(path: string, value: T) => {
    setSettings((prev) => setToPath({ ...prev }, path, value));
  }, []);

  const storeOption = useCallback(<T,>(path: string, value: T) => {
    setSettings((prev) => {
      const newSettings = setToPath({ ...prev }, path, value);
      storeLeaf(path, value);
      return newSettings;
    });
  }, []);

  // Memoize context value to prevent unnecessary re-renders
  const contextValue = useMemo(
    () => ({ getOption, setOption, storeOption, settings }),
    [getOption, setOption, storeOption, settings],
  );

  return (
    <SettingsContext.Provider value={contextValue}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return ctx;
};
