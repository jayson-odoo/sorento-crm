/**
 * TAG-TEMPLATE-DUPLICATE items 1, 5 and 6 on the Tag Templates list (owner 6 Nov).
 *
 * - Item 5: search, the Filters menu (Price type, Family, Status, all multi-select, each a chip)
 *   and New Template share the standard toolbar row; filters and every column's sort go to the
 *   SERVER; the row link carries the filters so the editor's pager can rebuild them.
 * - Item 1: a Duplicate row action copies the template and opens the copy in the editor.
 * - Item 6: drag handles only in the manual order and only for a template editor; a column sort
 *   hides them and says "Clear sort to reorder".
 *
 * The toolbar is stubbed to render its slots flat (its own menus have their own tests), and
 * `SearchableMultiSelect` to a native multi-select.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
  });
}

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/dealer-kit/tag-templates',
  useRouter: () => ({ push: nav.push, replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: vi.fn(() => 'x'),
  dismissDeferredToast: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('./TagTemplateDialog', () => ({ TagTemplateDialog: () => null }));
vi.mock('./AssignTemplateDialog', () => ({ AssignTemplateDialog: () => null }));

const perms = vi.hoisted(() => ({ manage: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => slug === 'dealer_kit.tag_templates.manage' && perms.manage,
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    'aria-label'?: string;
    value: string[];
    onChange: (v: string[]) => void;
    options: { value: string; label: string }[];
  }) => (
    <select
      multiple
      aria-label={props['aria-label']}
      value={props.value}
      onChange={(e) =>
        props.onChange(Array.from(e.target.selectedOptions).map((o) => o.value))
      }
    >
      {props.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/ui/data-grid-list-toolbar', () => ({
  DataGridListToolbar: (props: {
    searchSlot?: ReactNode;
    primaryAction?: ReactNode;
    filters?: {
      content: ReactNode;
      activeSummary?: { label: string; onClear: () => void }[];
    };
  }) => (
    <div data-testid="toolbar">
      {props.searchSlot}
      <div data-testid="filters">{props.filters?.content}</div>
      {(props.filters?.activeSummary ?? []).map((chip) => (
        <button key={chip.label} type="button" onClick={chip.onClear}>
          chip {chip.label}
        </button>
      ))}
      {props.primaryAction}
    </div>
  ),
}));

const svc = vi.hoisted(() => ({
  listTemplates: vi.fn(),
  duplicateTemplate: vi.fn(),
  reorderTemplates: vi.fn(),
}));
vi.mock('../../services/tagTemplateService', () => ({
  listTemplates: (...a: unknown[]) => svc.listTemplates(...a),
  duplicateTemplate: (...a: unknown[]) => svc.duplicateTemplate(...a),
  reorderTemplates: (...a: unknown[]) => svc.reorderTemplates(...a),
  deleteTemplate: vi.fn(),
  getTemplateUsage: vi.fn(),
  createTemplate: vi.fn(),
}));

import { TagTemplatesList } from './TagTemplatesList';

const tpl = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id,
  name,
  family: 'ala_carte',
  doc: { layers: [], width_mm: 85, height_mm: 58 },
  print_size: { width_mm: 85, height_mm: 58 },
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  published_version_id: null,
  published_version_no: null,
  price_type: 'list',
  ...over,
});

function draw() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TagTemplatesList />
    </QueryClientProvider>,
  );
}

const lastFilter = () => svc.listTemplates.mock.calls.at(-1)?.[0] ?? {};
const body = () => within(document.querySelector('tbody') as HTMLElement);

/** The header's own sort button (a column-drag wrapper may also carry role=button). */
function sortButton(header: HTMLElement): HTMLElement {
  return header.querySelector('button[data-slot="button"]') as HTMLElement;
}

function pick(label: string, values: string[]) {
  const select = screen.getByLabelText(label) as HTMLSelectElement;
  for (const option of Array.from(select.options)) option.selected = values.includes(option.value);
  fireEvent.change(select);
}

beforeEach(() => {
  perms.manage = true;
  nav.push.mockReset();
  toasts.success.mockReset();
  svc.listTemplates.mockReset().mockResolvedValue([tpl('a', 'BF_LP'), tpl('b', 'BF_SP')]);
  svc.duplicateTemplate.mockReset();
  svc.reorderTemplates.mockReset().mockResolvedValue(undefined);
});

describe('item 5: standard toolbar, server filters and sort', () => {
  it('puts search, the three filters and New Template in the one toolbar', async () => {
    draw();
    await screen.findByText('BF_SP');
    const bar = screen.getByTestId('toolbar');
    expect(within(bar).getByLabelText('Search templates')).toBeInTheDocument();
    expect(within(bar).getByLabelText('Price type')).toBeInTheDocument();
    expect(within(bar).getByLabelText('Family')).toBeInTheDocument();
    expect(within(bar).getByLabelText('Status')).toBeInTheDocument();
    expect(within(bar).getByRole('button', { name: /New Template/ })).toBeInTheDocument();
  });

  it('the Price type filter is multi-select and offers LP, SP, LP & SP and Not set', async () => {
    draw();
    await screen.findByText('BF_SP');
    const labels = Array.from(
      (screen.getByLabelText('Price type') as HTMLSelectElement).options,
    ).map((o) => o.textContent);
    expect(labels).toEqual(['LP', 'SP', 'LP & SP', 'Not set']);
    expect((screen.getByLabelText('Price type') as HTMLSelectElement).multiple).toBe(true);
  });

  it('sends every chosen filter value to the server, comma-joined, and shows a chip per filter', async () => {
    draw();
    await screen.findByText('BF_SP');
    pick('Price type', ['list', 'unset']);
    pick('Status', ['live', 'draft']);
    await waitFor(() =>
      expect(lastFilter()).toMatchObject({ price_type: 'list,unset', status: 'live,draft' }),
    );
    expect(screen.getByRole('button', { name: 'chip Price type: LP, Not set' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'chip Price type: LP, Not set' }));
    await waitFor(() => expect(lastFilter().price_type).toBeUndefined());
  });

  it('sorts on the server from every column header, Price type, Print Size and Status included', async () => {
    draw();
    await screen.findByText('BF_SP');
    expect(lastFilter().sort).toBeUndefined();
    for (const [title, id] of [
      ['Price type', 'price_type'],
      ['Print Size', 'print_size'],
      ['Status', 'published'],
      ['Name', 'name'],
    ]) {
      const header = screen.getAllByRole('columnheader').find((th) => th.textContent?.includes(title))!;
      fireEvent.click(sortButton(header));
      await waitFor(() => expect(lastFilter().sort).toBe(id));
    }
  });

  it('the row link carries the search for the editor pager', async () => {
    draw();
    await screen.findByText('BF_SP');
    fireEvent.change(screen.getByLabelText('Search templates'), { target: { value: 'BF' } });
    await waitFor(() => expect(lastFilter()).toMatchObject({ query: 'BF' }));
    fireEvent.click(body().getByText('BF_LP'));
    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    const params = new URLSearchParams(String(nav.push.mock.calls.at(-1)![0]).split('?')[1]);
    expect(params.get('query')).toBe('BF');
  });

  it('the row link carries the filters for the editor pager', async () => {
    draw();
    await screen.findByText('BF_SP');
    pick('Family', ['ala_carte']);
    await waitFor(() => expect(lastFilter()).toMatchObject({ family: 'ala_carte' }));
    fireEvent.click(body().getByText('BF_LP'));
    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    const href = String(nav.push.mock.calls.at(-1)![0]);
    expect(href).toContain('/dealer-kit/tag-templates/a?');
    expect(href).toContain('family=ala_carte');
  });
});

describe('item 1: duplicate', () => {
  it('copies the row and opens the copy in the editor, list state carried', async () => {
    svc.duplicateTemplate.mockResolvedValue(tpl('c', 'BF_LP (copy)'));
    draw();
    await screen.findByText('BF_SP');
    const row = body().getByText('BF_LP').closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: 'Duplicate template' }));

    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    expect(svc.duplicateTemplate).toHaveBeenCalledWith('a');
    expect(toasts.success).toHaveBeenCalledWith('Duplicated as BF_LP (copy)');
    expect(String(nav.push.mock.calls[0][0])).toMatch(/^\/dealer-kit\/tag-templates\/c\?/);
  });

  it('is not offered to a user who cannot edit templates', async () => {
    perms.manage = false;
    draw();
    await screen.findByText('BF_SP');
    expect(screen.queryByRole('button', { name: 'Duplicate template' })).toBeNull();
  });
});

describe('item 6: drag reorder', () => {
  it('shows a drag handle per row in the manual order for a template editor', async () => {
    draw();
    await screen.findByText('BF_SP');
    expect(screen.getAllByRole('button', { name: 'Drag to reorder' })).toHaveLength(2);
  });

  it('a column sort hides the handles and says to clear the sort; clearing brings them back', async () => {
    draw();
    await screen.findByText('BF_SP');
    const header = screen.getAllByRole('columnheader').find((th) => th.textContent?.includes('Name'))!;
    fireEvent.click(sortButton(header));
    await waitFor(() => expect(screen.queryAllByRole('button', { name: 'Drag to reorder' })).toHaveLength(0));
    expect(screen.getByText('Clear sort to reorder')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear sort' }));
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Drag to reorder' })).toHaveLength(2));
    expect(lastFilter().sort).toBeUndefined();
  });

  it('a viewer gets no handles', async () => {
    perms.manage = false;
    draw();
    await screen.findByText('BF_SP');
    expect(screen.queryAllByRole('button', { name: 'Drag to reorder' })).toHaveLength(0);
  });
});
