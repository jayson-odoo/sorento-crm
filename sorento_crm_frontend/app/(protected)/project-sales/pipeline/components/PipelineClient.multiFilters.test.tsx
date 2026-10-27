/**
 * FILTER-MULTISELECT PR6: the Pipeline Developer, Type and Approval filters take several values (OR); one set reaches the service,
 * clearing clears, an old single-value URL still reads.
 */
/**
 * PipelineClient - the filters moved into the toolbar.
 *
 * Developer, Type and "Critical only" used to sit in a bordered card ABOVE the grid
 * card, which is a second layout nobody else in the product uses. They are now the
 * grid toolbar's Filters popover with an active count, exactly as the users list does
 * it. Board view has no grid toolbar to host them, so it carries the same search box
 * and the same Filters button in one row instead.
 *
 * The view toggle and Start deliberately stay in the page header: they change what the
 * whole screen IS, which is not a list-toolbar job.
 *
 * Start replaces the old standalone "Register project" button (S2, R21): one page-level
 * button, top right, opening Register a project / Upload PO / Upload delivery schedule.
 * Rows carry no Start of their own.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
  useSearchParams: () => new URLSearchParams((globalThis as unknown as { __zztSearch?: string }).__zztSearch ?? ''),
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

vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { PipelineClient } from './PipelineClient';

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PipelineClient />
    </QueryClientProvider>,
  );
}

/** Radix opens its popovers on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  window.localStorage.clear();
  listProjects.mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1, limit: 50 },
  });
  listParties.mockResolvedValue({
    data: [{ id: 'd1', party_type: 'developer', name: 'SP Setia', is_active: true }],
    pagination: { total: 1, page: 1, limit: 200 },
  });
  listProjectTypes.mockResolvedValue([
    { id: 'ty1', name: 'Hotel', code: 'HOTEL', derives_delivery_from_launch: false, sort_order: 1, is_active: true },
  ]);
});

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : [String(v ?? '')]).flatMap((s) => s.split(',')).map((s) => s.trim()).filter(Boolean).sort();
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}

const last = () => {
  const args = listProjects.mock.calls.at(-1) as unknown[];
  return args.find((a) => a && typeof a === 'object') as Record<string, unknown>;
};
const FILTERS: [string, string, string][] = [['developer_party_id', 'd1', 'd2'], ['type_id', 'ty1', 'ty2'], ['approval_state', 'pending', 'rejected']];

describe('pipeline/components/PipelineClient.multiFilters.test.tsx - multi filters', () => {
  beforeEach(() => {
    (globalThis as unknown as { __zztSearch?: string }).__zztSearch = '';
    Element.prototype.scrollIntoView = vi.fn();
    listParties.mockResolvedValue({
      data: [
        { id: 'd1', party_type: 'developer', name: 'ZZT Dev One', is_active: true },
        { id: 'd2', party_type: 'developer', name: 'ZZT Dev Two', is_active: true },
      ],
      pagination: { total: 2, page: 1, limit: 200 },
    });
    listProjectTypes.mockResolvedValue([
      { id: 'ty1', name: 'Hotel', code: 'HOTEL', derives_delivery_from_launch: false, sort_order: 1, is_active: true },
      { id: 'ty2', name: 'Condo', code: 'CONDO', derives_delivery_from_launch: false, sort_order: 2, is_active: true },
    ]);
  });

  it.each(FILTERS)('%s is a multi control', async (_p, a) => {
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the service as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing, never an all value', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([a, b].sort()));
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([]));
    for (const [params] of listProjects.mock.calls) {
      expect(setOf((params as Record<string, unknown>)[param])).not.toContain('all');
    }
  });

  it('an old link with one value reads as one value, a joined one as a set', async () => {
    (globalThis as unknown as { __zztSearch?: string }).__zztSearch = 'developer_party_id=d1&type_id=ty1,ty2';
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    await waitFor(() => expect(setOf(last().developer_party_id)).toEqual(['d1']));
    expect(setOf(last().type_id)).toEqual(['ty1', 'ty2']);
  });
});
