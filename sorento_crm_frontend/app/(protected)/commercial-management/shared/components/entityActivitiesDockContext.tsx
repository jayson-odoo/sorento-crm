'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type EntityActivitiesDockRegistration = {
  variant: 'project' | 'master_quotation' | 'lead';
  entityId: string;
  canPost: boolean;
  leadIdForMessages?: string | null;
  className?: string;
};

type Ctx = {
  registration: EntityActivitiesDockRegistration | null;
  setRegistration: (r: EntityActivitiesDockRegistration | null) => void;
};

const EntityActivitiesDockContext = createContext<Ctx | null>(null);

export function EntityActivitiesDockProvider({ children }: { children: ReactNode }) {
  const [registration, setRegistrationState] = useState<EntityActivitiesDockRegistration | null>(null);

  const setRegistration = useCallback((r: EntityActivitiesDockRegistration | null) => {
    setRegistrationState(r);
  }, []);

  const value = useMemo(
    () => ({
      registration,
      setRegistration,
    }),
    [registration, setRegistration],
  );

  return <EntityActivitiesDockContext.Provider value={value}>{children}</EntityActivitiesDockContext.Provider>;
}

export function useEntityActivitiesDock() {
  const ctx = useContext(EntityActivitiesDockContext);
  if (!ctx) {
    throw new Error('useEntityActivitiesDock must be used within EntityActivitiesDockProvider');
  }
  return ctx;
}

/** Optional: host can avoid throwing when provider missing (should not happen in app shell). */
export function useEntityActivitiesDockOptional() {
  return useContext(EntityActivitiesDockContext);
}
