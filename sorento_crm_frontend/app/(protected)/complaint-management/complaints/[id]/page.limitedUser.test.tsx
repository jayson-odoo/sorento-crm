/**
 * PORTAL-P4-REQUESTS owner hand test 2 item 4 (red): a LIMITED user's complaint detail page has no page-level
 * Back button (the embedded portal form has its own top row); the breadcrumb is the way back. Staff keep Back.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/complaint-management/complaints/r-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/RecordEntityRegistrar', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/FormDetailTabsWithRevisions', () => ({ __esModule: true, default: () => null }));
vi.mock('../components/ComplaintDetail', () => ({ __esModule: true, default: () => null }));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

import Page from './page';

// Render the page's sync shell; drop async server children (not renderable on the client).
function prune(node: React.ReactNode): React.ReactNode {
  if (!React.isValidElement(node)) return node;
  const el = node as React.ReactElement<{ children?: React.ReactNode }>;
  if (typeof el.type === 'function' && el.type.constructor.name === 'AsyncFunction') return null;
  if (el.props.children === undefined) return el;
  return React.cloneElement(el, undefined, ...React.Children.toArray(el.props.children).map(prune));
}
const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      {prune(Page({ params: Promise.resolve({ id: 'r-1' }) }))}
    </QueryClientProvider>,
  );

beforeEach(() => {
  cleanup();
  held = new Set();
});

describe('complaint detail page header', () => {
  it('limited: no "Back to complaints" button, breadcrumb link back to the list is present', () => {
    held = new Set(['complaint_management.complaints.view_own']);
    mount();
    expect(screen.queryByRole('link', { name: /Back to complaints/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Back to complaints/i })).toBeNull();
    const crumbs = screen.getAllByRole('link').filter((a) => a.getAttribute('href')?.split('?')[0] === '/complaint-management/complaints');
    expect(crumbs.length).toBeGreaterThan(0);
  });

  it('staff: "Back to complaints" stays (pin)', () => {
    held = new Set(['complaint_management.complaints.view', 'complaint_management.complaints.view_own']);
    mount();
    expect(screen.getByRole('link', { name: /Back to complaints/i })).toBeInTheDocument();
  });
});
