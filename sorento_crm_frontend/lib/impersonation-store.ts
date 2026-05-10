"use client";

import { useSyncExternalStore } from 'react';

export type ImpersonationTargetUser = {
  id: string;
  name: string | null;
  email: string | null;
  avatar: string | null;
  role_name: string | null;
};

export type ImpersonationSession = {
  sessionId: string;
  startedAt: string;
  targetUser: ImpersonationTargetUser;
};

type Listener = () => void;

const STORAGE_KEY = 'impersonation-session-v1';

function _readPersisted(): ImpersonationSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ImpersonationSession;
  } catch {
    return null;
  }
}

function _writePersisted(session: ImpersonationSession | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (session) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore
  }
}

let _state: ImpersonationSession | null = _readPersisted();
const _listeners = new Set<Listener>();

function emit() {
  _listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      // ignore
    }
  });
}

export const impersonationStore = {
  getState(): ImpersonationSession | null {
    return _state;
  },
  setSession(session: ImpersonationSession | null): void {
    _state = session;
    _writePersisted(session);
    emit();
  },
  subscribe(fn: Listener): () => void {
    _listeners.add(fn);
    return () => {
      _listeners.delete(fn);
    };
  },
};

export function useImpersonationSession(): ImpersonationSession | null {
  return useSyncExternalStore(
    impersonationStore.subscribe,
    impersonationStore.getState,
    () => null,
  );
}
