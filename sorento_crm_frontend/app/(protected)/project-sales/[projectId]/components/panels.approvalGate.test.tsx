/**
 * PROJECT-REG-PORTAL review (final round): a tab on a portal registration that is still
 * waiting for approval (or was rejected) offers no add button, even to someone who may edit
 * the project, because the server refuses the write with 409 `project_not_approved`. One
 * table over the five panels the reviewer named, each checked against an approved control.
 *
 * The panels run on their real hooks over a stubbed `apiFetch` that answers every list with
 * an empty page, so what is pinned is the gate (`canWorkOnProject`), not a mock of it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({ data: [], items: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
        { status: 200 },
      ),
    ),
  ),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me' } }, status: 'authenticated' }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async () => ({ listing_key: 'k', config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, payload: unknown) => ({
    listing_key: listingKey,
    config: payload,
  })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

import { DeliverySchedulesPanel } from './DeliverySchedulesPanel';
import { ProjectDocumentsPanel } from './ProjectDocumentsPanel';
import { PurchaseOrdersPanel } from './PurchaseOrdersPanel';
import { SalesOrdersPanel } from './SalesOrdersPanel';
import { StakeholdersPanel } from './StakeholdersPanel';

function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PPF2610001',
    title: 'Gate Tower',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    approval_state: null,
    ...over,
  } as Project;
}

const PANELS: [string, (p: Project) => React.ReactElement, RegExp][] = [
  ['StakeholdersPanel', (p) => <StakeholdersPanel project={p} />, /Add stakeholder/],
  ['DeliverySchedulesPanel', (p) => <DeliverySchedulesPanel project={p} />, /Upload a schedule/],
  ['PurchaseOrdersPanel', (p) => <PurchaseOrdersPanel project={p} />, /Upload a PO document/],
  ['SalesOrdersPanel', (p) => <SalesOrdersPanel project={p} />, /Build drafts/],
  ['ProjectDocumentsPanel', (p) => <ProjectDocumentsPanel project={p} />, /Upload documents/],
];

function renderPanel(element: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

describe.each(PANELS)('%s on a registration waiting for a decision', (_name, make, button) => {
  it('an approved project offers the add button (the control)', async () => {
    renderPanel(make(project({ approval_state: 'approved' })));
    expect(await screen.findByRole('button', { name: button })).toBeInTheDocument();
  });

  it.each(['pending', 'rejected'] as const)('a %s one offers none, even to an editor', async (state) => {
    renderPanel(make(project({ approval_state: state, project_code: null, can_edit: true })));
    // Wait for the same render the control reached before reading the absence.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole('button', { name: button })).toBeNull();
  });
});
