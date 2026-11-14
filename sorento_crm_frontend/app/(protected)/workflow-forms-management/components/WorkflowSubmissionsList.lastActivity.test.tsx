/**
 * FORMS-LAST-ACTIVITY F1/F2/F5: the Workflow form submissions list shows a "Last activity" column (one line,
 * formatDateTimeInMalaysia, no "Revised" prefix) and sorts by it, newest first, by default.
 * Red test: written before the column exists. Fake data only.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn();

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/workflow-forms-management/submissions',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({ listing_key: listingKey, config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({ listing_key: listingKey, config })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => []),
}));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));
vi.mock('@/components/common/LookupBoundLabel', () => ({
  default: ({ value }: { value: string }) => <span>{value}</span>,
}));
vi.mock('@/hooks/useTenantModules', () => ({ useTenantModules: () => ({ enabledModuleKeys: null, isLoading: false }) }));
vi.mock('@/lib/list-query/listQueryService', () => ({ fetchListQueryFields: vi.fn(async () => []) }));
const grid = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useWorkflowForms', () => ({
  usePublishedWorkflowDefinitionsForSubmissionQuery: () => ({
    data: { data: [{ id: 'zzt-def', code: 'ZZT', name: 'ZZT Form', published_schema: { states: [{ code: 'zzt_draft', label: 'Draft' }] } }] },
  }),
  useWorkflowSubmissionsGridQuery: (...a: unknown[]) => grid(...a),
}));
import List from './WorkflowSubmissionsList';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

// A plain naive ISO string, like the API returns; the expectation goes through the same helper.
const STAMP = '2026-03-10T09:05:00';
const STAMP_TEXT = formatDateTimeInMalaysia(STAMP);
const ROW = { id: 'ws-1', definition_id: 'zzt-def', definition_name: 'ZZT Form', definition_code: 'ZZT', current_state_code: 'zzt_draft', header_data: {}, lines: [], created_at: '2026-01-01T00:00:00', updated_at: '2026-01-02T00:00:00', last_activity_at: STAMP };

beforeEach(() => {
  url.search = '';
  vi.clearAllMocks();
  grid.mockReset();
  grid.mockReturnValue({
    data: { data: [ROW], pagination: { total: 1, page: 1, limit: 25 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, isError: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <List fixedDefinitionId="zzt-def" />
    </QueryClientProvider>,
  );
}

describe('Workflow form submissions list - Last activity', () => {
  it('has a "Last activity" column header', async () => {
    renderList();
    await screen.findAllByText('ZZT Form');
    expect(screen.getAllByText('Last activity').length).toBeGreaterThan(0);
  });

  it('renders the stamp as dd/mm/yyyy, h:mm am/pm with no "Revised" prefix', async () => {
    renderList();
    expect(await screen.findByText(STAMP_TEXT)).toBeInTheDocument();
    expect(STAMP_TEXT).toMatch(/^\d{2}\/\d{2}\/\d{4}, \d{1,2}:\d{2} (am|pm)$/i);
    expect(screen.queryByText(/Revised/)).toBeNull();
  });

  it('first request sorts by last_activity_at, newest first', async () => {
    renderList();
    await screen.findAllByText('ZZT Form');
    await waitFor(() => expect(grid).toHaveBeenCalled());
    const first = grid.mock.calls[0][0] as { sorting?: Array<{ id: string; desc: boolean }> };
    expect(first.sorting).toEqual([{ id: 'last_activity_at', desc: true }]);
  });

  it('F5: the "Updated" column is now "Last activity"', async () => {
    renderList();
    await screen.findAllByText('ZZT Form');
    expect(screen.queryByText('Updated')).toBeNull();
    expect(screen.queryByText(formatDateTimeInMalaysia('2026-01-02T00:00:00'))).toBeNull();
  });
});
