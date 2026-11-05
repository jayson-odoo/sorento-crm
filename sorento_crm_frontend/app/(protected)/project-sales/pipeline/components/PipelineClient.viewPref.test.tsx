/**
 * PROJECTS-BOARD-VIEW-PREF: Pipeline (Dashboards > Project Sales > Projects) opens in the
 * view THIS user last picked, read from their server-side column-config row, and a
 * user who never picked still lands on the board.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

const listProjects = vi.fn();
const listParties = vi.fn();
const listProjectTypes = vi.fn();
const listingKeys: (string | null | undefined)[] = [];
const push = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/pipeline',
  useRouter: () => ({ push, replace: vi.fn() }),
  // The list restores its page, sort and filters from the query string Back hands
  // it (S3-01), so it reads the URL on every render.
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: async () => {}, isLoading: false };
  },
}));

vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph', () => ({
  useProjectStatusGraph: () => ({ data: { statuses: [] }, isLoading: false }),
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listProjects: (...args: unknown[]) => listProjects(...args),
    listParties: (...args: unknown[]) => listParties(...args),
    listProjectTypes: (...args: unknown[]) => listProjectTypes(...args),
    listProjectTemplates: vi.fn(async () => []),
    previewClashes: vi.fn(async () => ({ candidates: [] })),
    registerProject: vi.fn(),
    changeProjectStatus: vi.fn(),
  };
});

const granted = new Set(['projects.projects.edit', 'projects.registrations.submit', 'projects.projects.view']);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => granted.has(s)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

// Developer, Type and Approval are multi-selects now (FILTER-MULTISELECT PR6); a one-value pick stands in here.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string[];
    onChange: (next: string[]) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value[0] ?? ''}
      onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

// A per-user server row, keyed by the signed-in user: what the column-config endpoint
// holds. `currentUser` switches who is "signed in".
let currentUser = 'u1';
const serverRows = new Map<string, Record<string, unknown>>();
const getConfig = vi.fn(async (listingKey: string) => ({
  listing_key: listingKey,
  config: serverRows.get(`${currentUser}|${listingKey}`) ?? null,
}));
const putConfig = vi.fn(async (listingKey: string, payload: Record<string, unknown>) => {
  const k = `${currentUser}|${listingKey}`;
  const merged = { ...(serverRows.get(k) ?? {}), ...payload };
  serverRows.set(k, merged);
  return { listing_key: listingKey, config: merged };
});
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (key: string) => getConfig(key),
  upsertUserListColumnConfig: (key: string, payload: Record<string, unknown>) => putConfig(key, payload),
  resetUserListColumnConfig: vi.fn(),
}));

import { PipelineClient } from './PipelineClient';

const KEY = 'projects.projects.view::pipeline-view';

function renderClient() {
  // A fresh client per render is a fresh page load: nothing survives but the server row.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PipelineClient />
    </QueryClientProvider>,
  );
}

const gridButton = () => screen.getByRole('button', { name: /grid view/i });
const boardButton = () => screen.getByRole('button', { name: /board view/i });

beforeEach(() => {
  vi.clearAllMocks();
  serverRows.clear();
  currentUser = 'u1';
  window.localStorage.clear();
  listProjects.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 50 } });
  listParties.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 200 } });
  listProjectTypes.mockResolvedValue([]);
});

describe('PipelineClient remembers the view per user', () => {
  it('opens on the board for a user who never picked, and writes nothing', async () => {
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    expect(boardButton()).toHaveAttribute('aria-pressed', 'true');
    expect(listProjects.mock.calls[0][0]).toMatchObject({ limit: 200 });
    expect(putConfig).not.toHaveBeenCalled();
  });

  it('saves the pick on the server under the pipeline listing key', async () => {
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    fireEvent.click(gridButton());
    await waitFor(() => expect(putConfig).toHaveBeenCalledWith(KEY, { view: 'grid' }));
    expect(gridButton()).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens in the stored view after a reload, fetching only that view', async () => {
    const first = renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    fireEvent.click(gridButton());
    await waitFor(() => expect(putConfig).toHaveBeenCalled());
    first.unmount();
    listProjects.mockClear();

    renderClient();
    await waitFor(() => expect(gridButton()).toHaveAttribute('aria-pressed', 'true'));
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    // Held until the view was known: no wasted 200-row board fetch first.
    for (const [params] of listProjects.mock.calls) expect(params).toMatchObject({ limit: 50 });
  });

  it('does not share a row with the grid columns, so Reset columns cannot forget the view', async () => {
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    fireEvent.click(gridButton());
    await waitFor(() => expect(putConfig).toHaveBeenCalled());
    expect(KEY).not.toBe('projects.projects.view::pipeline');
    expect(putConfig.mock.calls.every(([key]) => key === KEY)).toBe(true);
  });

  it('a pick made before the stored view arrives wins over it', async () => {
    serverRows.set(`u1|${KEY}`, { view: 'board' });
    let release: () => void = () => {};
    getConfig.mockImplementationOnce(
      (key: string) =>
        new Promise((resolve) => {
          release = () => resolve({ listing_key: key, config: { view: 'board' } });
        }),
    );
    renderClient();
    fireEvent.click(gridButton());
    release();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(gridButton()).toHaveAttribute('aria-pressed', 'true');
  });

  it('clicking the view already shown writes nothing', async () => {
    serverRows.set(`u1|${KEY}`, { view: 'grid' });
    renderClient();
    await waitFor(() => expect(gridButton()).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(gridButton());
    await new Promise((r) => setTimeout(r, 20));
    expect(putConfig).not.toHaveBeenCalled();
  });

  it('while the stored view loads, neither view is shown or pressed (crew pass: no Board flash)', async () => {
    serverRows.set(`u1|${KEY}`, { view: 'grid' });
    let release: () => void = () => {};
    getConfig.mockImplementationOnce(
      (key: string) =>
        new Promise((resolve) => {
          release = () => resolve({ listing_key: key, config: { view: 'grid' } });
        }),
    );
    renderClient();
    expect(boardButton()).toHaveAttribute('aria-pressed', 'false');
    expect(gridButton()).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('pipeline-view-loading')).toBeInTheDocument();
    // No board scaffolding (its own search + Filters row) while unknown.
    expect(screen.queryByRole('button', { name: /filters/i })).toBeNull();
    release();
    await waitFor(() => expect(gridButton()).toHaveAttribute('aria-pressed', 'true'));
    expect(boardButton()).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByTestId('pipeline-view-loading')).toBeNull();
  });

  it('keeps a pick an older build stored in this browser when the server has none', async () => {
    window.localStorage.setItem('project-sales.pipeline.view', 'grid');
    renderClient();
    await waitFor(() => expect(gridButton()).toHaveAttribute('aria-pressed', 'true'));
  });

  it('the server value wins over the old browser value', async () => {
    window.localStorage.setItem('project-sales.pipeline.view', 'grid');
    serverRows.set(`u1|${KEY}`, { view: 'board' });
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    expect(boardButton()).toHaveAttribute('aria-pressed', 'true');
  });

  it('a failed read falls back to the board instead of hanging', async () => {
    getConfig.mockRejectedValueOnce(new Error('offline'));
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    expect(boardButton()).toHaveAttribute('aria-pressed', 'true');
  });
});
