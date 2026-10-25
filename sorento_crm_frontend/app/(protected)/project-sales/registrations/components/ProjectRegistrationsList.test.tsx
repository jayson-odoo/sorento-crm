/**
 * ProjectRegistrationsList (PROJECT-REG-PORTAL UAC B2, B3, G2).
 *
 * Service boundary mocked (`@/services/projectRegistrationService`); the real hooks and the
 * real DataGrid run. Expected service export: getProjectRegistrations.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
  ResizeObserverStub;
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
Element.prototype.scrollIntoView = vi.fn();

const services = vi.hoisted(() => ({ getProjectRegistrations: vi.fn() }));
vi.mock('@/services/projectRegistrationService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ...services,
}));

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn() }),
  usePathname: () => '/project-sales/registrations',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));
vi.mock(
  '@/lib/listing-column-preferences/listColumnPreferencesService',
  () => ({
    getUserListColumnConfig: vi.fn(async () => ({
      listing_key: 'k',
      config: null,
    })),
    upsertUserListColumnConfig: vi.fn(
      async (listingKey: string, payload: unknown) => ({
        listing_key: listingKey,
        config: payload,
      }),
    ),
    resetUserListColumnConfig: vi.fn(async () => undefined),
  }),
);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({
    permissions: [],
    permissionSet: new Set(),
    isLoading: false,
  }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    // eslint-disable-next-line no-restricted-syntax -- test stub for SearchableSelect
    <select
      aria-label="Status filter"
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      {props.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import ProjectRegistrationsList from './ProjectRegistrationsList';

const LONG_TITLE =
  'CADANGAN PEMBINAAN SEBUAH KILANG BARU DI ATAS LOT 9001, MUKIM TEBRAU, DAERAH JOHOR BAHRU, JOHOR DARUL TAKZIM';

const ROWS = [
  {
    id: 'reg-1',
    submitted_at: '2026-10-02T08:00:00',
    title: LONG_TITLE,
    developer_name: 'Example Developer Sdn Bhd',
    state: 'Johor',
    sales_agent_name: 'Aminah Example',
    status: 'pending' as const,
    possible_duplicates: [
      {
        project_id: 'proj-77',
        project_code: 'PPF2509012',
        title: 'KILANG ALPHA LOT 9001',
      },
      {
        project_id: 'proj-78',
        project_code: 'PRJ-000041',
        title: 'GUDANG BETA TEBRAU',
      },
    ],
    project_id: null,
    project_code: null,
  },
  {
    id: 'reg-2',
    submitted_at: '2026-10-03T08:00:00',
    title: 'MENARA ZETA',
    developer_name: null,
    state: 'Selangor',
    sales_agent_name: 'Bakar Example',
    status: 'approved' as const,
    possible_duplicates: [],
    project_id: 'proj-90',
    project_code: 'PPF2610001',
  },
];

function page(rows: typeof ROWS) {
  return { data: rows, pagination: { total: rows.length, page: 1, limit: 25 } };
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProjectRegistrationsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  services.getProjectRegistrations.mockReset();
  nav.push.mockReset();
});
afterEach(() => cleanup());

describe('ProjectRegistrationsList', () => {
  it('G2: shows the columns Date, Project title, Developer, State, Sales agent, Possible duplicate, Status', async () => {
    services.getProjectRegistrations.mockResolvedValue(page(ROWS));
    const { container } = renderList();

    await screen.findByText('MENARA ZETA');
    const headers = Array.from(container.querySelectorAll('thead th')).map(
      (th) => (th.textContent ?? '').trim(),
    );
    const wanted = [
      'Date',
      'Project title',
      'Developer',
      'State',
      'Sales agent',
      'Possible duplicate',
      'Status',
    ];
    const found = wanted.map((title) =>
      headers.findIndex((h) => h.includes(title)),
    );
    expect(found.every((i) => i >= 0)).toBe(true);
    expect([...found].sort((a, b) => a - b)).toEqual(found);
  });

  it('B3, G2: the sales agent is the NAME and each duplicate links to /project-sales/<project_id> as "<code> <title>"', async () => {
    services.getProjectRegistrations.mockResolvedValue(page(ROWS));
    renderList();

    const first = await screen.findByRole('link', {
      name: 'PPF2509012 KILANG ALPHA LOT 9001',
    });
    expect(first).toHaveAttribute('href', '/project-sales/proj-77');
    const second = screen.getByRole('link', {
      name: 'PRJ-000041 GUDANG BETA TEBRAU',
    });
    expect(second).toHaveAttribute('href', '/project-sales/proj-78');
    expect(screen.getByText('Aminah Example')).toBeInTheDocument();
  });

  it('G2: a row without duplicates has no duplicate link in its row', async () => {
    services.getProjectRegistrations.mockResolvedValue(page(ROWS));
    renderList();

    const row = (await screen.findByText('MENARA ZETA')).closest(
      'tr',
    ) as HTMLElement;
    const hrefs = within(row)
      .queryAllByRole('link')
      .map((a) => a.getAttribute('href'));
    expect(hrefs.filter((h) => h?.startsWith('/project-sales/proj-'))).toEqual(
      [],
    );
  });

  it('G2: the grid is fixed layout and long text is truncated with a title', async () => {
    services.getProjectRegistrations.mockResolvedValue(page(ROWS));
    const { container } = renderList();

    await screen.findByText('MENARA ZETA');
    const table = container.querySelector('table') as HTMLElement;
    expect(table.className + table.style.tableLayout).toMatch(
      /table-fixed|fixed/,
    );
    const title = screen.getByText(LONG_TITLE);
    expect(title).toHaveAttribute('title', LONG_TITLE);
    expect(title.className).toMatch(/truncate/);
  });

  it('G2: opening a row goes to its review page', async () => {
    services.getProjectRegistrations.mockResolvedValue(page(ROWS));
    renderList();

    const cell = await screen.findByText('MENARA ZETA');
    fireEvent.click(cell);
    expect(nav.push).toHaveBeenCalledTimes(1);
    expect(String(nav.push.mock.calls[0][0])).toMatch(
      /^\/project-sales\/registrations\/reg-2/,
    );
  });

  it('B2: opens on the pending queue (the server default status)', async () => {
    services.getProjectRegistrations.mockResolvedValue(page(ROWS));
    renderList();

    await screen.findByText('MENARA ZETA');
    expect(services.getProjectRegistrations).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'pending' }),
    );
  });

  it('empty state: heading, no button inside the empty block', async () => {
    services.getProjectRegistrations.mockResolvedValue(page([]));
    renderList();

    const heading = await screen.findByText(/no registrations/i);
    const block = heading.parentElement as HTMLElement;
    expect(block.querySelector('button')).toBeNull();
  });

  it('error state: a failed load shows an error and a retry', async () => {
    services.getProjectRegistrations.mockRejectedValue(
      new Error('Failed to load registrations'),
    );
    renderList();

    expect(
      await screen.findByText(/failed to load registrations/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /retry|try again/i }),
    ).toBeInTheDocument();
  });

  it('loading state: renders no rows and no empty message before the data arrives', async () => {
    services.getProjectRegistrations.mockReturnValue(new Promise(() => {}));
    renderList();

    expect(screen.queryByText(/no registrations/i)).toBeNull();
    expect(screen.queryByText('MENARA ZETA')).toBeNull();
  });
});
