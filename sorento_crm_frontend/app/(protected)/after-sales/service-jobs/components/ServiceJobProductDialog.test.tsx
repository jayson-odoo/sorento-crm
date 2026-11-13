/**
 * AFTER-SALES-P2 red tests (UAC F1, J): the Add product / Edit product dialog.
 *
 * Module the coder builds: `./ServiceJobProductDialog` default export, props
 *   { open: boolean; onOpenChange(open): void; jobId: string; line?: Line | null }   (line set = Edit)
 * Fields, in order, each a SearchableSelect with aria-label (Kind and Defect `clearable`) except the date:
 *   Product (async, `fetchOptions` over `searchCatalogueProducts(query)`), Kind, Purchase date (shared DatePicker,
 *   dd/mm/yyyy), Defect. Buttons: Cancel and the main button ("Add product" when adding, "Save" when editing).
 * Services it reads (all mocked here):
 *   `../services/serviceJobService`: searchCatalogueProducts(q) -> {id, product_code, product_name}[],
 *                                    getDefectOptions() -> {id, label}[]
 *   `../../warranty/services/warrantyConfigService`: testKindRules(productId) -> { resolved_kind: {id, code, name} | null, deciding_rule },
 *                                    getKinds(params) -> { data: {id, name, ...}[] }
 * Mutations from `../hooks/useServiceJobProducts`: useServiceJobProductMutations(jobId) -> { add, update } (mutateAsync).
 *   add.mutateAsync({ product_id, kind_id, purchase_date: 'YYYY-MM-DD'|null, defect_type_id })
 *   update.mutateAsync({ lineId, values: { kind_id, purchase_date, defect_type_id } })
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

type Opt = { value: string; label: string };
/** Stand-in for the repo's SearchableSelect: a native select over static or fetched options, plus a clear button. */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: {
    value: string; onChange: (v: string) => void; onOptionChange?: (o: Opt | null) => void; options?: Opt[];
    fetchOptions?: (q: string, i: number) => Promise<Opt[]>; selectedOption?: Opt; clearable?: boolean; 'aria-label'?: string;
  }) => {
    const [fetched, setFetched] = React.useState<Opt[]>([]);
    React.useEffect(() => { p.fetchOptions?.('', 0).then(setFetched); }, []); // eslint-disable-line
    const all = [...(p.options ?? []), ...fetched, ...(p.selectedOption ? [p.selectedOption] : [])];
    return (
      <span>
        <select
          aria-label={p['aria-label']}
          value={p.value}
          onChange={(e) => { p.onChange(e.target.value); p.onOptionChange?.(all.find((o) => o.value === e.target.value) ?? null); }}
        >
          <option value="">-</option>
          {all.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {p.clearable && p.value ? (
          <button type="button" aria-label={`Clear ${p['aria-label']}`} onClick={() => { p.onChange(''); p.onOptionChange?.(null); }} />
        ) : null}
      </span>
    );
  },
}));

const searchCatalogueProducts = vi.fn();
vi.mock('../services/serviceJobService', () => ({
  searchCatalogueProducts: (...a: unknown[]) => searchCatalogueProducts(...a),
  getDefectOptions: vi.fn(async () => [{ id: 'd-1', label: 'Leakage' }, { id: 'd-2', label: 'Rust' }]),
}));
const testKindRules = vi.fn();
vi.mock('../../warranty/services/warrantyConfigService', () => ({
  testKindRules: (...a: unknown[]) => testKindRules(...a),
  getKinds: vi.fn(async () => ({
    data: [{ id: 'k-1', name: 'Water Closet', code: 'WC' }, { id: 'k-2', name: 'Booster Pump', code: 'BP' }],
    pagination: { total: 2, page: 1, limit: 100 },
  })),
}));

const add = { mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };
const update = { mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };
vi.mock('../hooks/useServiceJobProducts', () => ({ useServiceJobProductMutations: () => ({ add, update }) }));

import ServiceJobProductDialog from './ServiceJobProductDialog';

const LINE = {
  id: 'line-1', product_id: 'p-1', product_code: 'DEMO-WC-02', product_name: 'Demo one piece water closet',
  kind_id: 'k-1', kind_name: 'Water Closet', purchase_date: '2020-03-15', defect_type_id: 'd-1', defect_label: 'Leakage', sort_order: 0,
};
const onOpenChange = vi.fn();

function setup(line: typeof LINE | null = null) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ServiceJobProductDialog open onOpenChange={onOpenChange} jobId="j-1" line={line as never} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  searchCatalogueProducts.mockResolvedValue([{ id: 'p-1', product_code: 'DEMO-WC-02', product_name: 'Demo one piece water closet' }]);
  testKindRules.mockResolvedValue({ resolved_kind: { id: 'k-1', code: 'WC', name: 'Water Closet' }, deciding_rule: { id: 'r-1' } });
});

describe('ServiceJobProductDialog', () => {
  it('add mode: the main button is disabled until a product is picked', async () => {
    setup();
    expect(screen.getByRole('button', { name: 'Add product', hidden: false })).toBeDisabled();
    await screen.findByRole('option', { name: /DEMO-WC-02/ });
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'p-1' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Add product' })).toBeEnabled());
  });

  it('picking a product prefills Kind from the rule suggestion, and Kind stays changeable and clearable', async () => {
    setup();
    await screen.findByRole('option', { name: /DEMO-WC-02/ });
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'p-1' } });
    await waitFor(() => expect(testKindRules).toHaveBeenCalledWith('p-1'));
    await waitFor(() => expect(screen.getByLabelText('Kind')).toHaveValue('k-1'));
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'k-2' } });
    expect(screen.getByLabelText('Kind')).toHaveValue('k-2');
    fireEvent.click(screen.getByRole('button', { name: 'Clear Kind' }));
    expect(screen.getByLabelText('Kind')).toHaveValue('');
  });

  it('submits the picked product with the four backend keys', async () => {
    setup();
    await screen.findByRole('option', { name: /DEMO-WC-02/ });
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'p-1' } });
    await waitFor(() => expect(screen.getByLabelText('Kind')).toHaveValue('k-1'));
    fireEvent.change(screen.getByLabelText('Defect'), { target: { value: 'd-2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add product' }));
    await waitFor(() =>
      expect(add.mutateAsync).toHaveBeenCalledWith({
        product_id: 'p-1', kind_id: 'k-1', purchase_date: null, defect_type_id: 'd-2',
      }),
    );
  });

  it('edit mode: pre-fills the line, the date as dd/mm/yyyy, and saves with update', async () => {
    setup(LINE);
    expect(screen.getByLabelText('Kind')).toHaveValue('k-1');
    expect(screen.getByLabelText('Defect')).toHaveValue('d-1');
    expect(screen.getByDisplayValue('15/03/2020')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear Defect' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(update.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ lineId: 'line-1', values: { kind_id: 'k-1', purchase_date: '2020-03-15', defect_type_id: null } }),
      ),
    );
  });

  it('shows no UUID and Cancel closes without saving', () => {
    setup(LINE);
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(update.mutateAsync).not.toHaveBeenCalled();
  });
});
