/**
 * AI-PROMPTS-STD-VIEWS: the prompts list on the standard DataGrid listing.
 *
 * Pins: every data column sorts SERVER-side (the sort reaches the list query), the Status and
 * Runs on filters are multi-selects behind the toolbar's Filters popover and reach the query,
 * the search reaches the query, the row opens the prompt (rowHref carrying the list state),
 * dates read dd/mm/yyyy, and the domain-block-out-of-date banner still stands above the grid.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PromptsList } from './PromptsList';
import type { PromptListRow } from '../../services/aiPromptsService';

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
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

const usePromptList = vi.fn();
const usePromptBlocksStatus = vi.fn();
const useHasPermission = vi.fn();

vi.mock('../../hooks/useAIAssistantPrompts', () => ({
  usePromptList: (params: unknown) => usePromptList(params),
}));
vi.mock('../../hooks/usePromptBlocksStatus', () => ({
  usePromptBlocksStatus: () => usePromptBlocksStatus(),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => useHasPermission(),
}));
const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/ai-assistant/prompts',
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
// A native multiple <select> stands in for the Radix multi-select, labelled by its id.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    id,
    value = [],
    onChange,
    options = [],
  }: {
    id?: string;
    value?: string[];
    onChange?: (v: string[]) => void;
    options?: Array<{ value: string; label: string }>;
  }) => (
    <select
      multiple
      aria-label={id}
      value={value}
      onChange={(e) => onChange?.(Array.from(e.target.selectedOptions, (o) => o.value))}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const ROWS: PromptListRow[] = [
  {
    id: 'reformulator',
    name: 'reformulator',
    role: 'Rewrite turn',
    active: true,
    activates_in: null,
    variables: ['current_date'],
    dry_runnable: true,
    production_version: 3,
    staging_version: null,
    latest_version: 4,
    updated_at: '2026-07-03T09:00:00Z',
    updated_by_name: 'Jay',
    provider: 'openai',
    model: 'gpt-5.4-mini',
  },
  {
    id: 'planner',
    name: 'planner',
    role: 'Decompose task',
    active: false,
    activates_in: 'M2.5',
    variables: [],
    dry_runnable: false,
    production_version: 1,
    staging_version: null,
    latest_version: 1,
    updated_at: null,
    updated_by_name: null,
    provider: null,
    model: null,
  },
];

function listResult(rows = ROWS) {
  return {
    data: { data: rows, empty: rows.length === 0, pagination: { total: rows.length, page: 1 }, model_options: ['gpt-5.4-mini'] },
    isLoading: false,
    isFetching: false,
    isPlaceholderData: false,
    error: null,
    refetch: vi.fn(),
  };
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PromptsList />
    </QueryClientProvider>,
  );
}

const lastParams = () => usePromptList.mock.calls[usePromptList.mock.calls.length - 1][0];

function pointer(el: Element) {
  fireEvent.pointerDown(el, { button: 0, ctrlKey: false, pointerType: 'mouse' });
}

beforeEach(() => {
  usePromptList.mockReset().mockReturnValue(listResult());
  usePromptBlocksStatus.mockReset().mockReturnValue({ data: { stale: false } });
  useHasPermission.mockReset().mockReturnValue(true);
});
afterEach(() => cleanup());

describe('PromptsList (standard DataGrid)', () => {
  it('shows forbidden when the user lacks permission', () => {
    useHasPermission.mockReturnValue(false);
    renderList();
    expect(screen.getByText(/don't have permission/i)).toBeInTheDocument();
  });

  it('renders every prompt, active and dormant, as grid rows', () => {
    renderList();
    expect(screen.getByText('reformulator')).toBeInTheDocument();
    expect(screen.getByText('planner')).toBeInTheDocument();
    expect(screen.getByText('Dormant (M2.5)')).toBeInTheDocument();
    expect(screen.getByText('gpt-5.4-mini')).toBeInTheDocument();
    expect(screen.getByText('Default model')).toBeInTheDocument();
    expect(screen.getByText('v3')).toBeInTheDocument();
    expect(screen.getByText('v4')).toBeInTheDocument();
  });

  it('shows dates as dd/mm/yyyy through the shared formatter', () => {
    renderList();
    expect(screen.getByText(/^03\/07\/2026/)).toBeInTheDocument();
  });

  it('drops the hand-rolled table and the Show inactive toggle', () => {
    renderList();
    expect(screen.queryByTestId('active-prompts-table')).not.toBeInTheDocument();
    expect(screen.queryByTestId('show-inactive-toggle')).not.toBeInTheDocument();
    expect(screen.queryByText(/Every prompt the assistant uses is versioned here/)).not.toBeInTheDocument();
  });

  it.each([
    ['Prompt', 'name'],
    ['Role', 'role'],
    ['Status', 'status'],
    ['Runs on', 'model'],
    ['Production', 'production_version'],
    ['Latest', 'latest_version'],
    ['Last edited', 'updated_at'],
    ['Edited by', 'updated_by_name'],
  ])('sorts by %s on the server', async (title, sortId) => {
    renderList();
    // The list opens sorted by name A-Z, so the first press on Prompt flips it to Z-A and on
    // any other header sorts that column A-Z.
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${title}$`) }));
    await waitFor(() => expect(lastParams().sorting).toEqual([{ id: sortId, desc: sortId === 'name' }]));
  });

  it('passes the search box through to the list query', async () => {
    vi.useFakeTimers();
    try {
      renderList();
      fireEvent.change(screen.getByPlaceholderText(/Search prompts/i), { target: { value: 'parser' } });
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });
      expect(lastParams().searchQuery).toBe('parser');
    } finally {
      vi.useRealTimers();
    }
  });

  it('filters by several statuses at once (multi-select)', async () => {
    renderList();
    pointer(screen.getByRole('button', { name: /^Filters/ }));
    const status = (await screen.findByLabelText('prompt-status-filter')) as HTMLSelectElement;
    for (const o of Array.from(status.options)) o.selected = true;
    fireEvent.change(status);
    await waitFor(() => expect(lastParams().status).toEqual(['active', 'dormant']));
  });

  it('filters by several models at once, including the default model', async () => {
    renderList();
    pointer(screen.getByRole('button', { name: /^Filters/ }));
    const model = (await screen.findByLabelText('prompt-model-filter')) as HTMLSelectElement;
    expect(Array.from(model.options).map((o) => o.value)).toEqual(['default', 'gpt-5.4-mini']);
    for (const o of Array.from(model.options)) o.selected = true;
    fireEvent.change(model);
    await waitFor(() => expect(lastParams().model).toEqual(['default', 'gpt-5.4-mini']));
  });

  it('opens the prompt from the row, carrying the list state for Back and the pager', () => {
    push.mockReset();
    renderList();
    fireEvent.click(screen.getByText('Rewrite turn'));
    expect(push).toHaveBeenCalledTimes(1);
    const href = String(push.mock.calls[0][0]);
    expect(href.startsWith('/system-management/ai-assistant/prompts/reformulator?')).toBe(true);
    expect(href).toMatch(/page=1/);
    expect(href).toMatch(/sort=name/);
  });

  it('carries both filters into the row URL, so Back and the pager page the same filtered set', async () => {
    push.mockReset();
    renderList();
    pointer(screen.getByRole('button', { name: /^Filters/ }));
    const status = (await screen.findByLabelText('prompt-status-filter')) as HTMLSelectElement;
    for (const o of Array.from(status.options)) o.selected = true;
    fireEvent.change(status);
    const model = screen.getByLabelText('prompt-model-filter') as HTMLSelectElement;
    for (const o of Array.from(model.options)) o.selected = true;
    fireEvent.change(model);
    await waitFor(() => expect(lastParams().model).toEqual(['default', 'gpt-5.4-mini']));
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    fireEvent.click(screen.getByText('Rewrite turn'));
    const href = new URL(String(push.mock.calls.at(-1)![0]), 'http://x');
    expect(href.searchParams.get('status')).toBe('active,dormant');
    expect(href.searchParams.get('model')).toBe('default,gpt-5.4-mini');
  });

  it('offers Odoo-style row selection', () => {
    renderList();
    expect(screen.getByRole('checkbox', { name: /Select reformulator/i })).toBeInTheDocument();
  });

  it('keeps the domain-block-out-of-date banner above the grid', () => {
    usePromptBlocksStatus.mockReturnValue({ data: { stale: true, published_version: 7 } });
    renderList();
    const banner = screen.getByTestId('domain-block-stale-banner');
    expect(banner).toHaveTextContent(/Domain block out of date/);
    expect(banner).toHaveTextContent(/v7/);
    expect(screen.getByRole('link', { name: 'chatbot_semantic_parser' })).toHaveAttribute(
      'href',
      '/system-management/ai-assistant/prompts/chatbot_semantic_parser',
    );
  });
});
