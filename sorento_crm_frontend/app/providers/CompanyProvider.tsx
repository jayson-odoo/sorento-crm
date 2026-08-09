'use client';

/**
 * ============================================================================
 * CompanyProvider — active-company context (Phase 2, live backend)
 * ============================================================================
 * `company` is a data-partition dimension below tenant (Sorento + Mocha share
 * one deployment). See documentation/plans/PLAN-multi-company-isolation.md.
 *
 * Source of truth:
 *  - Switchable companies (grants) come from GET /companies/my-context.
 *  - The ACTIVE company is the NextAuth JWT claim `session.user.active_company_id`
 *    (seeded at login, re-minted on switch), falling back to my-context's
 *    resolved active/last-active for the first render after login.
 *  - setActiveCompany() persists server-side (POST /companies/switch) then
 *    re-mints the token via useSession().update({ active_company_id }) so the
 *    claim — not localStorage — is authoritative across reloads/tabs.
 * ============================================================================
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { toast } from 'sonner';
import {
  getMyCompanyContext,
  switchCompany,
} from '@/app/(protected)/system-management/companies/services/companyService';

export interface ActiveCompany {
  id: string;
  name: string;
  code: string;
  is_active: boolean;
}

interface CompanyContextValue {
  /** Companies the current user is allowed to switch into. */
  companies: ActiveCompany[];
  /** Same list — kept explicit so callers reason about switchable grants. */
  grants: ActiveCompany[];
  /** The active company, or null when the user has no company grants / still loading. */
  activeCompany: ActiveCompany | null;
  setActiveCompany: (companyId: string) => void;
  isLoading: boolean;
}

const CompanyContext = createContext<CompanyContextValue | null>(null);

export function CompanyProvider({ children }: { children: ReactNode }) {
  const { data: session, status, update } = useSession();
  const queryClient = useQueryClient();
  const isAuthenticated = status === 'authenticated';

  // Switchable companies (full objects) come from my-context; the active-company
  // claim rides on the session JWT.
  const { data: context, isLoading: contextLoading } = useQuery({
    queryKey: ['company-my-context'],
    queryFn: getMyCompanyContext,
    enabled: isAuthenticated,
    staleTime: 30 * 1000,
    // The active company is a SERVER fact on a row several sessions can write (one dev
    // account, one `last_active_company_id`). A five-minute cache with focus refetching off
    // is how the header came to name one company while every API call was scoped to
    // another. Re-read on focus so returning to the tab cannot show a stale company.
    refetchOnWindowFocus: true,
    retry: 1,
  });

  const grants = useMemo<ActiveCompany[]>(
    () =>
      (context?.companies ?? []).map((c) => ({
        id: c.id,
        name: c.name,
        code: c.code,
        is_active: c.is_active,
      })),
    [context],
  );

  // Optimistic override so a switch reflects instantly before the token re-mints.
  const [pendingId, setPendingId] = useState<string | null>(null);

  // BACKEND FIRST. `my-context.active_company_id` is what the scope resolver itself
  // resolved, so the header states what the API is actually scoped to. The session claim is
  // only a fallback for the first render after a switch, before my-context re-reads.
  const resolvedActiveId =
    pendingId ?? context?.active_company_id ?? session?.user?.active_company_id ?? null;

  const activeCompany = useMemo<ActiveCompany | null>(() => {
    if (grants.length === 0) return null;
    // No `?? grants[0]`. Falling back to whichever company sorted first is how the chip
    // came to read "Sorento" while the backend was serving Mocha - and an empty screen is
    // then blamed on the screen. Naming no company is honest; naming the wrong one is not.
    return grants.find((c) => c.id === resolvedActiveId) ?? null;
  }, [grants, resolvedActiveId]);

  const setActiveCompany = useCallback(
    (companyId: string) => {
      if (!grants.some((c) => c.id === companyId)) return;
      if (companyId === activeCompany?.id) return;
      const previous = activeCompany?.id ?? null;
      setPendingId(companyId);
      void (async () => {
        try {
          await switchCompany(companyId);
          // Re-mint the JWT so the active-company claim is authoritative. This
          // MUST complete before we refetch — the backend scope resolver prefers
          // the token's active_company_id claim over persisted last_active, so a
          // refetch on the OLD token would still be scoped to the previous company.
          await update({ active_company_id: companyId });
          // Every company-scoped list is now stale - force a refetch under the new
          // company so the UI reflects the switch without a manual reload. my-context
          // included: it is the source the header now reads, so leaving it cached would
          // leave the chip on the old company until the next focus.
          await queryClient.invalidateQueries();
          const next = grants.find((c) => c.id === companyId);
          toast.success(next ? `Switched to ${next.name}` : 'Company switched');
        } catch (e) {
          setPendingId(previous); // revert optimistic override
          toast.error(e instanceof Error ? e.message : 'Failed to switch company');
        }
      })();
    },
    [grants, activeCompany, update, queryClient],
  );

  const value = useMemo<CompanyContextValue>(
    () => ({
      companies: grants,
      grants,
      activeCompany,
      setActiveCompany,
      isLoading: !isAuthenticated || contextLoading,
    }),
    [grants, activeCompany, setActiveCompany, isAuthenticated, contextLoading],
  );

  return <CompanyContext.Provider value={value}>{children}</CompanyContext.Provider>;
}

export function useCompany(): CompanyContextValue {
  const ctx = useContext(CompanyContext);
  if (!ctx) {
    throw new Error('useCompany must be used inside <CompanyProvider>');
  }
  return ctx;
}
