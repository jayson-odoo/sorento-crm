import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

/** TOWN-V2: the Town page is admin-only (`dashboards.town.view`); anyone else gets Access denied. */
const perms = vi.hoisted(() => ({ set: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: perms.set, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() }),
}));
vi.mock('@/app/components/common/AccessDenied', () => ({ default: () => <div>Access denied</div> }));

import TownLayout from './layout';

describe('Town layout', () => {
  it('shows Access denied without dashboards.town.view', () => {
    perms.set = new Set(['sales.reports.view']);
    render(<TownLayout><div>the town</div></TownLayout>);
    expect(screen.getByText('Access denied')).toBeTruthy();
    expect(screen.queryByText('the town')).toBeNull();
  });

  it('renders the town with dashboards.town.view', () => {
    perms.set = new Set(['dashboards.town.view']);
    render(<TownLayout><div>the town</div></TownLayout>);
    expect(screen.getByText('the town')).toBeTruthy();
  });
});
