'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import { FloatingAction } from './FloatingAction';

export interface PrimaryAction {
  label: string;
  onAction: () => void;
  blockedReason?: string | null;
  headerRef: RefObject<HTMLElement | null>;
}

type Register = (action: PrimaryAction) => () => void;

const PrimaryActionContext = createContext<Register | null>(null);

/**
 * Holds at most ONE registered primary action (R16) and renders the single FloatingAction from it.
 * Nothing renders when none is registered. The last registration wins; an unregister only clears
 * its own entry, so a header that unmounts after the next page's header mounted does not clear it.
 */
export function PrimaryActionHost({ children }: { children: ReactNode }) {
  const [action, setAction] = useState<PrimaryAction | null>(null);

  const register = useCallback<Register>((next) => {
    setAction(next);
    return () => setAction((current) => (current === next ? null : current));
  }, []);

  return (
    <PrimaryActionContext.Provider value={register}>
      {children}
      {action && (
        <FloatingAction
          label={action.label}
          onAction={action.onAction}
          blockedReason={action.blockedReason}
          headerPrimaryRef={action.headerRef}
        />
      )}
    </PrimaryActionContext.Provider>
  );
}

/**
 * For the v2 page headers: registers the header's primary on mount and update, unregisters on
 * unmount. Pass null for a page without a primary. A no-op outside the v2 shell.
 */
export function useRegisterPrimaryAction(action: PrimaryAction | null) {
  const register = useContext(PrimaryActionContext);
  // The handler can change every render; the registration must not, or it would loop.
  const onActionRef = useRef(action?.onAction);
  onActionRef.current = action?.onAction;

  const present = action !== null;
  const label = action?.label;
  const blockedReason = action?.blockedReason;
  const headerRef = action?.headerRef;

  const entry = useMemo<PrimaryAction | null>(
    () =>
      present && label !== undefined && headerRef
        ? { label, blockedReason, headerRef, onAction: () => onActionRef.current?.() }
        : null,
    [present, label, blockedReason, headerRef],
  );

  useEffect(() => {
    if (!register || !entry) return;
    return register(entry);
  }, [register, entry]);
}
