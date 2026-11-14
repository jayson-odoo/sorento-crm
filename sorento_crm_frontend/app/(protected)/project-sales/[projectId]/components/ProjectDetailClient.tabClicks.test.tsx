/**
 * RELATED-RECORDS-B hotfix (owner, 14 Nov): "when i click on related tab, I can't go to any other
 * tab". Open a project, click Related, then click every other tab: each one must open. The same
 * must hold after Back from a Related record (the address lands on `?tab=related&rel_*`).
 *
 * The page is the real ProjectDetailClient with the real RelatedRecordsPanel; the other panels are
 * stubs (each has its own tests). The address bar is a small store the mocked router writes, as
 * Next's router does, and a router write lands inside a transition, so a still-mounted Related
 * panel sees the page's new tab before it unmounts (that is how the bug showed in the browser).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const url = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const state = {
    search: '',
    writes: [] as string[],
    set(search: string) {
      state.search = search;
      listeners.forEach((l) => l());
    },
    subscribe(l: () => void) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
  return state;
});

vi.mock('next/navigation', async () => {
  const React = await import('react');
  const replace = (href: string) => {
    url.writes.push(href);
    url.set(href.split('?')[1] ?? '');
  };
  return {
    useRouter: () => ({ push: vi.fn(), replace, back: vi.fn() }),
    usePathname: () => '/project-sales/p1',
    useSearchParams: () => {
      const search = React.useSyncExternalStore(url.subscribe, () => url.search);
      return React.useMemo(() => new URLSearchParams(search), [search]);
    },
  };
});

vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/hooks/useLookupSetOptions', () => ({ useLookupSetOptions: () => ({ options: [] }) }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph', () => ({
  useProjectStatusGraph: () => ({ data: undefined }),
}));

const { stub } = vi.hoisted(() => ({
  stub: (name: string) =>
    function Stub() {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      return require('react').createElement('div', { 'data-testid': `panel-${name}` });
    },
}));
vi.mock('./ProjectActivityPanel', () => ({ ProjectActivityPanel: stub('activity') }));
vi.mock('./ProjectDocumentsPanel', () => ({ ProjectDocumentsPanel: stub('documents') }));
vi.mock('./ProjectAccessPanel', () => ({ ProjectAccessPanel: () => null }));
vi.mock('./CriticalPanel', () => ({ CriticalPanel: () => null }));
vi.mock('./PurchaseOrdersPanel', () => ({ PurchaseOrdersPanel: stub('orders') }));
vi.mock('./SalesOrdersPanel', () => ({ SalesOrdersPanel: stub('sales-orders') }));
vi.mock('./QuotationsPanel', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  QuotationsPanel: stub('quotations'),
}));
vi.mock('./SampleRequestsPanel', () => ({ SampleRequestsPanel: stub('sample-requests') }));
vi.mock('./StakeholdersPanel', () => ({ StakeholdersPanel: stub('stakeholders') }));
vi.mock('./TasksPanel', () => ({ TasksPanel: stub('tasks') }));

const projectFixture = vi.hoisted(() => ({
  id: 'p1',
  project_code: 'PRJ-ZZT-0001',
  title: 'Zzt Harbour View',
  outcome: 'open',
  is_critical: false,
  brands: [],
  brand_ids: [],
  next_action_overdue: false,
  stale_level: 0,
  is_unattended: false,
  open_task_count: 0,
  can_edit: true,
  approval_state: 'approved',
  status_id: 's-quoted',
  status_key: 'quoted',
  status_label: 'Quoted',
}) as unknown as Project);

vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const { response } = await import('./relatedRecordsTestKit');
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    useProject: () => ({ data: projectFixture, isLoading: false, isError: false }),
    usePartyRoles: () => ({ data: [] }),
    useChangeProjectStatus: () => ({ mutate: vi.fn(), isPending: false }),
    useSetProjectOutcome: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteProject: () => ({ mutateAsync: vi.fn() }),
    useUpdateProject: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
    useProjectRelatedRecords: () => ({
      data: response(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
    useSponsorshipRollup: () => ({ data: undefined, isLoading: false, isError: false, error: null }),
  };
});

import { ProjectDetailClient } from './ProjectDetailClient';

/** Every tab but Related and Overview, with the panel each one shows. */
const OTHER_TABS: Array<[label: string, panel: string]> = [
  ['Documents', 'documents'],
  ['Proposals', 'quotations'],
  ['Samples Request', 'sample-requests'],
  ['PO', 'orders'],
  ['SO', 'sales-orders'],
  ['Stakeholders', 'stakeholders'],
  ['Tasks', 'tasks'],
  ['Activity', 'activity'],
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProjectDetailClient projectId="p1" />
    </QueryClientProvider>,
  );
}

function clickTab(label: string) {
  const tab = screen.getByRole('tab', { name: new RegExp(`^${label}`) });
  act(() => {
    // Radix tabs select on mousedown; the router write runs as a transition, as Next's does.
    React.startTransition(() => {
      fireEvent.mouseDown(tab, { button: 0, ctrlKey: false });
    });
  });
}

const tabParam = () => new URLSearchParams(url.search).get('tab');

beforeEach(() => {
  url.search = '';
  url.writes.length = 0;
});

describe('project tabs after Related', () => {
  it.each(OTHER_TABS)('click Related, then %s opens %s', (label, panel) => {
    renderPage();
    clickTab('Related');
    expect(tabParam()).toBe('related');

    clickTab(label);

    expect(tabParam()).toBe(panel);
    expect(screen.getByTestId(`panel-${panel}`)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: new RegExp(`^${label}`) })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('click Related, then every other tab in turn, then Overview: each one opens', () => {
    renderPage();
    clickTab('Related');
    for (const [label, panel] of OTHER_TABS) {
      clickTab(label);
      expect(tabParam(), `after clicking ${label}`).toBe(panel);
      clickTab('Related');
      expect(tabParam()).toBe('related');
    }
    clickTab('Overview');
    expect(tabParam()).toBeNull();
    expect(screen.getByRole('tab', { name: /^Overview/ })).toHaveAttribute('aria-selected', 'true');
  });

  it.each(OTHER_TABS)(
    'Back from a Related record lands on Related; then %s opens %s',
    (label, panel) => {
      // Back restores the address the grid wrote before the record was opened.
      url.search = 'tab=related&rel_sort=number&rel_dir=asc';
      renderPage();
      expect(screen.getByRole('tab', { name: /^Related/ })).toHaveAttribute(
        'aria-selected',
        'true',
      );

      clickTab(label);

      expect(tabParam()).toBe(panel);
      expect(screen.getByTestId(`panel-${panel}`)).toBeInTheDocument();
    },
  );

  it('the retired ?tab=sponsorships link opens Related, then PO opens', () => {
    url.search = 'tab=sponsorships';
    renderPage();
    expect(tabParam()).toBe('related');
    clickTab('PO');
    expect(tabParam()).toBe('orders');
    expect(screen.getByTestId('panel-orders')).toBeInTheDocument();
  });
});
