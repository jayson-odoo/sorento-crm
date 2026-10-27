/**
 * FILTER-MULTISELECT PR7: Workflow submissions State code (quick filter) is a multi dropdown (it was a text box);
 * two values reach the grid query comma-joined and the text box is gone. Options come from the definition's
 * schema states, so the test scopes the list to one definition whose published schema carries three states.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/x',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));

vi.mock('@/hooks/useTenantModules', () => ({ useTenantModules: () => ({ enabledModuleKeys: null, isLoading: false }) }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/list-query/listQueryService', () => ({ fetchListQueryFields: vi.fn(async () => []) }));
const grid = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useWorkflowForms', () => ({
  usePublishedWorkflowDefinitionsForSubmissionQuery: () => ({
    data: {
      data: [{
        id: 'zzt-def', code: 'ZZT', name: 'ZZT Form',
        published_schema: { states: [{ code: 'zzt_draft', label: 'Draft' }, { code: 'zzt_review', label: 'Review' }, { code: 'zzt_done', label: 'Done' }] },
      }],
    },
  }),
  useWorkflowSubmissionsGridQuery: (...a: unknown[]) => grid(...a),
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


import WorkflowSubmissionsList from './WorkflowSubmissionsList';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : [String(v ?? '')]).flatMap((s) => s.split(',')).map((s) => s.trim()).filter(Boolean).sort();
const multis = () => screen.queryAllByRole('listbox').filter((el) => el.hasAttribute('multiple')) as HTMLSelectElement[];
async function multiAt(index: number) {
  await waitFor(() => {
    if (multis().length <= index) throw new Error(`no multi control at position ${index}, found ${multis().length}`);
  });
  return multis()[index];
}
const firstTwo = (el: HTMLSelectElement) => Array.from(el.options).slice(0, 2).map((o) => o.value);
function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
}
afterEach(() => cleanup());

const last = () => grid.mock.calls.at(-1)?.[0] as Record<string, unknown>;
beforeEach(() => {
  vi.clearAllMocks();
  grid.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 25 } }, isLoading: false, isPlaceholderData: false,
    isError: false, error: null, refetch: vi.fn(), isFetching: false,
  });
});
function open() {
  render(<QueryClientProvider client={client()}><WorkflowSubmissionsList fixedDefinitionId="zzt-def" /></QueryClientProvider>);
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Quick filters' }), { button: 0, ctrlKey: false });
}

describe('Workflow submissions - multi State code', () => {
  it('the text box is gone', async () => {
    open();
    await screen.findByText('Quick filters'); // the popover is open
    await waitFor(() => expect(screen.queryByPlaceholderText('e.g. submitted')).toBeNull());
  });

  it('two state codes reach the grid query comma-joined', async () => {
    const user = userEvent.setup();
    open();
    const el = await multiAt(0);
    await user.selectOptions(el, firstTwo(el));
    await waitFor(() => expect(setOf(last().quickStateCode)).toEqual(firstTwo(el).sort()));
  });
});
