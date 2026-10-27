/**
 * FILTER-MULTISELECT PR6 (resources): the attachment list's Folder, Company and Attachment type filters take
 * several values (OR); each reaches the list query as one set, clearing clears.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/usePermissions')>()),
  useHasPermission: () => true,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/resource-management/attachments',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
const h = vi.hoisted(() => ({
  calls: [] as Record<string, unknown>[],
  mutation: () => ({ mutate: () => {}, mutateAsync: async () => {}, isPending: false }),
}));
vi.mock('../hooks/useAttachments', () => ({
  useAttachments: (params: Record<string, unknown>) => {
    h.calls.push(params);
    return {
      data: { data: [], pagination: { total: 0, page: 1, limit: 50, totalPages: 0 } },
      isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
    };
  },
  useAttachmentTypesList: () => ({
    data: [{ id: 'zzt-t1', type_name: 'ZZT Type One' }, { id: 'zzt-t2', type_name: 'ZZT Type Two' }],
  }),
  useDirectoryTree: () => ({
    data: [
      { id: 'zzt-f1', name: 'ZZT Folder One', parent_id: null, sort_order: 0, created_at: '', children: [] },
      { id: 'zzt-f2', name: 'ZZT Folder Two', parent_id: null, sort_order: 1, created_at: '', children: [] },
    ],
  }),
  useBulkRestoreAttachments: h.mutation,
}));
vi.mock('../actions', () => ({ useAttachmentActions: () => ({ actions: [], dialogs: null }) }));
vi.mock('@/app/providers/CompanyProvider', () => ({
  useCompany: () => ({
    grants: [{ id: 'zzt-c1', name: 'ZZT Co One' }, { id: 'zzt-c2', name: 'ZZT Co Two' }], activeCompanyId: null, companies: [],
  }),
}));
vi.mock('./AttachmentUploadDialog', () => ({ default: () => null }));
vi.mock('./AttachmentBulkImportDialog', () => ({ default: () => null }));
vi.mock('./AttachmentBulkDeleteDialog', () => ({ default: () => null }));
vi.mock('./EditAttachmentTypeDialog', () => ({ default: () => null }));
vi.mock('./SetCompanyDialog', () => ({ default: () => null, SHARED_COMPANY_VALUE: 'shared' }));
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


import AttachmentBrowser from './AttachmentBrowser';

const last = () => h.calls[h.calls.length - 1];
function renderBrowser() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AttachmentBrowser />
    </QueryClientProvider>,
  );
}

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
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
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
}

beforeEach(() => {
  h.calls.length = 0;
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation((q: string) => ({
    matches: false, media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(),
    removeListener: vi.fn(), dispatchEvent: vi.fn(),
  })));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.unstubAllGlobals());

const FILTERS: [string, string, string][] = [
  ['directory_id', 'zzt-f1', 'zzt-f2'],
  ['company', 'zzt-c1', 'zzt-c2'],
  ['attachment_type_id', 'zzt-t1', 'zzt-t2'],
];
const valueOf = (param: string) =>
  param === 'attachment_type_id' ? (last().attachment_type_ids ?? last().attachment_type_id) : last()[param];

describe('Attachment browser - multi filters', () => {
  it.each(FILTERS)('%s is a multi control', async (_p, a) => {
    renderBrowser();
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the query as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderBrowser();
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(valueOf(param))).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing, never an all value', async (param, a, b) => {
    const user = userEvent.setup();
    renderBrowser();
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(valueOf(param))).toEqual([a, b].sort()));
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(valueOf(param))).toEqual([]));
  });
});
