/**
 * FILTER-MULTISELECT PR6 (resources): the drive panel's Attachment type, Storage status, Company and Uploaded by
 * filters take several values (OR); each reaches the drive query as one set, clearing clears.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Delete controls read the caller's permissions (ATTACH-DELETE-PERM); grant them here.
vi.mock('@/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/usePermissions')>()),
  useHasPermission: () => true,
}));
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DndContext } from '@dnd-kit/core';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/resource-management/attachment-directories',
  useSearchParams: () => new URLSearchParams(''),
}));

const h = vi.hoisted(() => {
  const tree = [
    {
      id: 'mkt',
      name: 'Marketing',
      parent_id: null,
      sort_order: 0,
      created_at: '',
      children: [
        { id: 'camp', name: 'Campaigns', parent_id: 'mkt', sort_order: 0, created_at: '', children: [] },
      ],
    },
  ];
  return {
    tree,
    driveCalls: [] as Record<string, unknown>[],
    treeState: { data: tree as unknown[], isSuccess: true, isFetching: false, isLoading: false },
    mutation: () => ({ mutate: () => {}, mutateAsync: async () => {}, isPending: false }),
  };
});
const tree = h.tree as AttachmentDirectoryTreeNode[];
vi.mock('../../attachments/hooks/useAttachments', () => ({
  useDriveContents: (params: Record<string, unknown>) => {
    h.driveCalls.push(params);
    return {
      data: { data: [], pagination: { total: 0, page: 1, limit: 50, totalPages: 0 } },
      isLoading: false,
      isPlaceholderData: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    };
  },
  useDirectoryTree: () => h.treeState,
  useDownloadAttachment: h.mutation,
  useRestoreAttachment: h.mutation,
  useBulkRestoreAttachments: h.mutation,
  useRestoreDirectory: h.mutation,
  useUpdateAttachment: h.mutation,
  useCreateDirectory: h.mutation,
  useUpdateDirectory: h.mutation,
  useDeleteDirectory: h.mutation,
  useMoveDirectory: h.mutation,
  useBulkMoveAttachments: h.mutation,
  useUploadAttachment: h.mutation,
  useBulkImportAttachment: h.mutation,
  useDeleteAttachment: h.mutation,
  useArchiveAttachment: h.mutation,
  useBulkArchiveAttachments: h.mutation,
  useBulkDeleteAttachments: h.mutation,
  usePermanentDeleteDirectory: h.mutation,
  useResubmitAttachmentWebhook: h.mutation,
  useAttachmentTypesList: () => ({ data: [] }),
  useAttachments: () => ({ data: undefined }),
  useReorderAttachments: h.mutation,
}));
vi.mock('../../attachment-types/hooks/useAttachmentTypes', () => ({
  useAttachmentTypes: () => ({
    data: { data: [{ id: 'zzt-t1', type_name: 'ZZT Type One' }, { id: 'zzt-t2', type_name: 'ZZT Type Two' }] },
  }),
}));
vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));
vi.mock('@/app/providers/CompanyProvider', () => ({
  useCompany: () => ({
    grants: [{ id: 'zzt-c1', name: 'ZZT Co One' }, { id: 'zzt-c2', name: 'ZZT Co Two' }], activeCompanyId: null, companies: [],
  }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: async () => [{ id: 'zzt-u1', name: 'ZZT User One' }, { id: 'zzt-u2', name: 'ZZT User Two' }],
}));

// The panel's dialogs are closed in every test here; stub them so their own providers
// (upload manager, etc.) are not needed.
vi.mock('../../attachments/components/AttachmentUploadDialog', () => ({ default: () => null }));
vi.mock('../../attachments/components/AttachmentBulkImportDialog', () => ({ default: () => null }));
vi.mock('../../attachments/components/AttachmentBulkDownloadDialog', () => ({ default: () => null }));
vi.mock('../../attachments/components/AttachmentDetailModal', () => ({ default: () => null }));

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

import AttachmentsInFolderPanel from './AttachmentsInFolderPanel';

const last = () => h.driveCalls[h.driveCalls.length - 1];
function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DndContext>
        <AttachmentsInFolderPanel directoryId="camp" onSelectFolder={vi.fn()} />
      </DndContext>
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
  fireEvent.pointerDown(screen.getByRole('button', { name: /^filters/i }), { button: 0, ctrlKey: false });
}

beforeEach(() => {
  h.driveCalls.length = 0;
  h.treeState = { data: tree, isSuccess: true, isFetching: false, isLoading: false };
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation((q: string) => ({
    matches: false, media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(),
    removeListener: vi.fn(), dispatchEvent: vi.fn(),
  })));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.unstubAllGlobals());

// [param on the drive query, two option values]
const FILTERS: [string, string, string][] = [
  ['attachment_type_id', 'zzt-t1', 'zzt-t2'],
  ['storage_status', 'accessible', 'missing'],
  ['company', 'zzt-c1', 'zzt-c2'],
  ['uploaded_by', 'zzt-u1', 'zzt-u2'],
];
const valueOf = (param: string) =>
  param === 'attachment_type_id' ? (last().attachment_type_ids ?? last().attachment_type_id) : last()[param];

describe('Attachments in folder panel - multi filters', () => {
  it.each(FILTERS)('%s is a multi control', async (_p, a) => {
    renderPanel();
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the query as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderPanel();
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(valueOf(param))).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing, never an all value', async (param, a, b) => {
    const user = userEvent.setup();
    renderPanel();
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(valueOf(param))).toEqual([a, b].sort()));
    await user.keyboard('{Escape}');
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(valueOf(param))).toEqual([]));
  });
});
