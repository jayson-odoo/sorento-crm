/**
 * This dropdown is the ONLY nav path to `/user-management/contacts` - that route
 * has no sidebar or mega-menu entry - so once `GET /contacts/` is gated on
 * `user_management.contacts.view` (and `GET /access-agents/` on
 * `user_management.access_agents.view`), an unfiltered quick link sends roles
 * holding neither slug to a grid that can only 403.
 *
 * Radix's dropdown primitives are stubbed to render inline, matching the pattern
 * in FormSkipAction.test.tsx; the filtering under test is the component's own.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { AppsDropdownMenu } from './apps-dropdown-menu';

const usePermissions = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => usePermissions(),
}));

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function grant(...slugs: string[]) {
  usePermissions.mockReturnValue({
    permissions: slugs,
    permissionSet: new Set(slugs),
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  });
}

function renderMenu() {
  render(<AppsDropdownMenu trigger={<button type="button">Apps</button>} />);
}

beforeEach(() => {
  usePermissions.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('apps quick links', () => {
  it('hides the two gated destinations from a caller holding neither slug', () => {
    grant('order_management.orders.view');

    renderMenu();

    expect(screen.queryByText('Internal Users')).toBeNull();
    expect(screen.queryByText('AI Agents')).toBeNull();
  });

  it('shows each gated destination to a caller holding its slug', () => {
    grant('user_management.contacts.view', 'user_management.access_agents.view');

    renderMenu();

    expect(screen.getByText('Internal Users')).toBeTruthy();
    expect(screen.getByText('AI Agents')).toBeTruthy();
  });

  it('shows only the destination whose slug the caller holds', () => {
    grant('user_management.contacts.view');

    renderMenu();

    expect(screen.getByText('Internal Users')).toBeTruthy();
    expect(screen.queryByText('AI Agents')).toBeNull();
  });

  it('leaves the ungated quick links alone, including while permissions load', () => {
    usePermissions.mockReturnValue({
      permissions: [],
      permissionSet: new Set<string>(),
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    renderMenu();

    expect(screen.getByText('Dashboard')).toBeTruthy();
    expect(screen.getByText('Delivery Orders')).toBeTruthy();
    expect(screen.getByText('Permissions')).toBeTruthy();
    expect(screen.queryByText('Internal Users')).toBeNull();
  });
});
