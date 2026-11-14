/**
 * AFTER-SALES-P2 red tests (UAC F1, J): the Products card on the job page, Details tab.
 *
 * Module the coder builds: `./ServiceJobProductsCard` default export, props `{ jobId: string; canEdit: boolean }`.
 * Reads from `../hooks/useServiceJobProducts` (new file):
 *   useServiceJobProducts(jobId) -> { data: Line[] | undefined, isLoading, isError, refetch }
 *     Line = { id, product_id, product_code, product_name, kind_id, kind_name, purchase_date ('YYYY-MM-DD'|null),
 *              defect_type_id, defect_label, sort_order }
 * Remove is the deferred countdown: `useDeferredRowAction` from `@/hooks/useDeferredRowAction`, `run({ id, subject })`,
 * no confirm() and no AlertDialog. Add / Edit open `./ServiceJobProductDialog` (props `{ open, onOpenChange, jobId, line }`).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const lines = vi.fn();
vi.mock('../hooks/useServiceJobProducts', () => ({
  useServiceJobProducts: () => lines(),
  useServiceJobProductMutations: () => ({
    add: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false },
  }),
}));

const run = vi.fn();
const deferredInputs: Record<string, unknown>[] = [];
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    deferredInputs.push(input);
    return { run, targetId: null, isPending: false, countdown: null };
  },
  useRowPending: () => () => false,
}));

vi.mock('./ServiceJobProductDialog', () => ({
  default: ({ open, line }: { open: boolean; line?: { id: string } | null }) =>
    open ? <div role="dialog">Product dialog {line ? `edit ${line.id}` : 'add'}</div> : null,
}));

import ServiceJobProductsCard from './ServiceJobProductsCard';

const LINE = {
  id: 'line-1', product_id: 'prod-uuid-1', product_code: 'DEMO-WC-02', product_name: 'Demo one piece water closet',
  kind_id: 'kind-uuid-1', kind_name: 'Water Closet', purchase_date: '2020-03-15', defect_type_id: 'def-uuid-1',
  defect_label: 'Leakage', sort_order: 0,
};
const LINE_2 = {
  ...LINE, id: 'line-2', product_id: 'prod-uuid-2', product_code: 'DEMO-PMP-05', product_name: 'Demo booster pump',
  kind_id: null, kind_name: null, purchase_date: null, defect_type_id: null, defect_label: null, sort_order: 1,
};

function renderCard(canEdit = true) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ServiceJobProductsCard jobId="j-1" canEdit={canEdit} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  deferredInputs.length = 0;
  lines.mockReturnValue({ data: [LINE, LINE_2], isLoading: false, isError: false, refetch: vi.fn() });
});

describe('ServiceJobProductsCard', () => {
  it('has the title and the five columns in the agreed order', () => {
    renderCard();
    expect(screen.getByText('Products')).toBeInTheDocument();
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent || '').trim()).filter(Boolean);
    expect(heads).toEqual(['Product code', 'Description', 'Kind', 'Purchase date', 'Defect']);
  });

  it('shows one line per product with the date as dd/mm/yyyy', () => {
    renderCard();
    const row = screen.getByText('DEMO-WC-02').closest('tr')!;
    for (const t of ['Demo one piece water closet', 'Water Closet', '15/03/2020', 'Leakage']) {
      expect(within(row).getByText(t)).toBeInTheDocument();
    }
    expect(screen.getByText('DEMO-PMP-05').closest('tr')).not.toBe(row);
  });

  it('shows a dash for a missing kind, date and defect', () => {
    renderCard();
    const row = screen.getByText('DEMO-PMP-05').closest('tr')!;
    expect(within(row).getAllByText('-')).toHaveLength(3);
  });

  it('renders no UUID anywhere', () => {
    const { container } = renderCard();
    expect(container.textContent).not.toMatch(/uuid|[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('shows a skeleton while loading', () => {
    lines.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    const { container } = renderCard();
    expect(container.querySelector('[data-slot="skeleton"]')).not.toBeNull();
  });

  it('shows an error message when the lines cannot be loaded', () => {
    lines.mockReturnValue({ data: undefined, isLoading: false, isError: true, refetch: vi.fn() });
    renderCard();
    expect(screen.getByText(/failed to load|could not load|couldn.t load/i)).toBeInTheDocument();
  });

  it('empty state is a heading and a hint with no button inside it', () => {
    lines.mockReturnValue({ data: [], isLoading: false, isError: false, refetch: vi.fn() });
    renderCard();
    const heading = screen.getByRole('heading', { name: /no products/i });
    expect(within(heading.parentElement as HTMLElement).queryByRole('button')).toBeNull();
    expect((heading.parentElement as HTMLElement).textContent!.length).toBeGreaterThan(heading.textContent!.length);
    // the one CTA stays in the card header
    expect(screen.getByRole('button', { name: 'Add product' })).toBeInTheDocument();
  });

  it('Add product opens the dialog for a dispatcher and is absent without edit rights', () => {
    const { unmount } = renderCard(true);
    fireEvent.click(screen.getByRole('button', { name: 'Add product' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('add');
    unmount();
    renderCard(false);
    expect(screen.queryByRole('button', { name: 'Add product' })).toBeNull();
  });

  it('right-click offers Edit and Remove; Edit opens the dialog on that line', async () => {
    renderCard();
    fireEvent.contextMenu(screen.getByText('DEMO-WC-02'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getAllByRole('menuitem').map((i) => (i.textContent || '').trim())).toEqual(['Edit', 'Remove']);
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('edit line-1');
  });

  it('Remove starts the deferred countdown with no confirm dialog', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderCard();
    fireEvent.contextMenu(screen.getByText('DEMO-WC-02'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove' }));
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ id: 'line-1' }));
    expect(String(deferredInputs[0].actionKey)).toMatch(/delete|remove/);
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('a read-only viewer gets no context menu', () => {
    renderCard(false);
    fireEvent.contextMenu(screen.getByText('DEMO-WC-02'));
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
