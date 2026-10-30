/**
 * PORTAL-P3-ROLE-MENU round 4, R5: the search dialog hands the account profile's salesperson block
 * to the universal-search context (a salesperson sees MY REQUESTS kinds, staff do not).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const profile: { salesperson: { portalKinds: string[]; portalSlug: string } | null } = {
  salesperson: null,
};
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: ['x'], permissionSet: new Set(['x']), isLoading: false }),
}));
vi.mock('@/hooks/useTenantModules', () => ({
  useTenantModules: () => ({ enabledModuleKeys: null, isLoading: false }),
}));
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => false }));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({ ...profile, isLoading: false, isError: false }),
}));
const runUniversalSearch = vi.fn(async () => ({}));
vi.mock('@/lib/universal-search', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/universal-search')>();
  return { ...original, runUniversalSearch: (...a: unknown[]) => (runUniversalSearch as (...x: unknown[]) => unknown)(...a) };
});

import { SearchDialog } from './search-dialog';

function lastContext(): Record<string, unknown> {
  const calls = runUniversalSearch.mock.calls as unknown as unknown[][];
  return calls[calls.length - 1][2] as Record<string, unknown>;
}

beforeEach(() => vi.clearAllMocks());

describe('SearchDialog salesperson context', () => {
  it('salesperson: context carries portalKinds', async () => {
    profile.salesperson = { portalKinds: ['stock_inquiry', 'complaint'], portalSlug: 'S1' };
    render(<SearchDialog trigger={<button>t</button>} />);
    await waitFor(() => expect(runUniversalSearch).toHaveBeenCalled());
    expect(lastContext().salesperson).toEqual({ portalKinds: ['stock_inquiry', 'complaint'] });
  });

  it('staff: context salesperson is null', async () => {
    profile.salesperson = null;
    render(<SearchDialog trigger={<button>t</button>} />);
    await waitFor(() => expect(runUniversalSearch).toHaveBeenCalled());
    expect(lastContext().salesperson).toBeNull();
  });
});
