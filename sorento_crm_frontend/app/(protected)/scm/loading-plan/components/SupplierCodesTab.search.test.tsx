/**
 * S1 / S5 / S6 - the Supplier codes tab gets a search box, and the Remembered table loses a
 * column and shortens another (`PLAN-scm-ui-feedback-14sep.md`, J1 and J4).
 *
 * TEST-FIRST. At the time this file is written `SupplierCodesTab` has NO search box at all,
 * its card titles read a bare `(n)`, `matchedToLabel` prints `CODE - Product name`, and the
 * Remembered table still carries a `How` column. Every test here is expected to be red until
 * S1/S5/S6 land.
 *
 * What the search is FOR (J1): a JINBAICHUAN stock list runs to sixty-odd unknown codes, and
 * the buyer is looking for the one they are on the phone about. Both tables narrow, because
 * "have I already ruled on this?" and "do I still have to?" are the same question asked twice
 * on one screen.
 *
 * The mocks are `SupplierCodesTab.test.tsx`'s, unchanged - same hook surface, same flattened
 * `SearchableSelect`, same DataGrid-in-jsdom stub for `useListingColumnPreferences`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const deferred = vi.hoisted(() => ({
  inputs: [] as Record<string, unknown>[],
  run: vi.fn(),
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    deferred.inputs.push(input);
    return { run: deferred.run, targetId: null, isPending: false };
  },
  useRowPending: () => () => false,
}));

const state = {
  rows: [] as unknown[],
  aliases: [] as unknown[],
  match: vi.fn(),
  dismiss: vi.fn(),
  undo: vi.fn(),
  rematch: vi.fn(),
  confirm: vi.fn(),
};

vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useUnmatchedSupplierCodes: () => ({ data: state.rows, isLoading: false }),
  useSupplierCodeAliases: () => ({ data: state.aliases, isLoading: false }),
  useMatchSupplierCodeInPlace: () => ({ mutateAsync: state.match, isPending: false }),
  useDismissSupplierCodeInPlace: () => ({ mutateAsync: state.dismiss, isPending: false }),
  useUndoSupplierCodeDecision: () => ({ mutate: state.undo, isPending: false }),
  useRematchSupplierCodes: () => ({ mutate: state.rematch, isPending: false }),
  useConfirmSupplierCodeDecisions: () => state.confirm,
}));

vi.mock(
  '@/app/(protected)/master-data-management/products/services/productService',
  () => ({
    getProducts: vi.fn(async () => ({
      data: [{ id: 'p-1', product_code: 'SRTWC286-SH', product_name: 'One piece toilet' }],
    })),
  }),
);

vi.mock(
  '@/app/(protected)/master-data-management/product-sets/services/productSetService',
  () => ({
    getProductSets: vi.fn(async () => ({
      data: [{ id: 's-1', set_code: 'CWC605-RL', name: 'Close-coupled WC' }],
    })),
  }),
);

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    onOptionChange,
    disabled,
    fetchOptions,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    onOptionChange?: (opt: { value: string; label: string } | null) => void;
    disabled?: boolean;
    fetchOptions?: (q: string, p: number) => Promise<{ value: string; label: string }[]>;
  }) => {
    const [options, setOptions] = React.useState<{ value: string; label: string }[]>([]);
    React.useEffect(() => {
      void fetchOptions?.('', 0).then(setOptions);
    }, [fetchOptions]);
    return (
      <select
        id={id}
        aria-label="Product"
        value={value}
        disabled={disabled}
        onChange={(e) => {
          const opt = options.find((o) => o.value === e.target.value) ?? null;
          onChange?.(e.target.value);
          onOptionChange?.(opt);
        }}
      >
        <option value="">Choose</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import { SupplierCodesTab } from './SupplierCodesTab';
import type { PlanDocumentKind } from '../../services/fulfilmentService';

const row = (over: Record<string, unknown> = {}) => ({
  item_code: 'SRTWC286-SH-250UF',
  product_name: '连体马桶',
  brand: 'SORENTO',
  spec: '纸箱包装',
  qty_packed: 400,
  qty_unfinished: 0,
  as_of: '2026-08-20',
  ...over,
});

const alias = (over: Record<string, unknown> = {}) => ({
  id: 'a-1',
  supplier_code: 'SRTWC8357-RL-300',
  product_code: 'SRTWC8357-300-RL',
  product_name: 'One piece toilet',
  set_code: null,
  set_name: null,
  source: 'manual',
  matched_by: 'manual',
  created_by: 'Ms Tee',
  created_at: '2026-08-27T02:00:00',
  ...over,
});

/** The two cards, so a code that appears in both tables can be asked about in one. */
function cardTitled(pattern: RegExp): HTMLElement {
  const title = screen.getByText(pattern);
  const card = title.closest('[data-slot="card"]');
  if (!card) throw new Error(`no card around ${pattern}`);
  return card as HTMLElement;
}

const needsCard = () => cardTitled(/^Needs a decision \(/);
const rememberedCard = () => cardTitled(/^Remembered \(/);

/** The box, by the label AC-1.1 names it under. */
function searchBox(): HTMLInputElement {
  return screen.getByLabelText('Search supplier codes') as HTMLInputElement;
}

function typeSearch(text: string) {
  fireEvent.change(searchBox(), { target: { value: text } });
}

function renderTab(
  documentLabel = 'Stock list 27/07/2026',
  documentKind: PlanDocumentKind = 'stock_list',
  statementAsOf: string | null = '2026-07-27',
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const buildTree = () => (
    <QueryClientProvider client={qc}>
      <SupplierCodesTab
        planId="plan-1"
        supplierId="sup-1"
        documentKind={documentKind}
        documentLabel={documentLabel}
        statementAsOf={statementAsOf}
      />
    </QueryClientProvider>
  );
  const utils = render(buildTree());
  return { ...utils, rerenderSame: () => utils.rerender(buildTree()) };
}

/** The three codes the queue holds in most of these tests. */
const QUEUE = [
  row({ item_code: 'CWC605-RL-250', product_name: '180横排连体马桶', brand: 'SORENTO' }),
  row({ item_code: 'CWC250-SH', product_name: '挂墙式马桶', brand: 'SORENTO' }),
  row({ item_code: 'SRTWT6801-P', product_name: '洗手盆', brand: 'DAFUYUAN' }),
];

beforeEach(() => {
  state.rows = [...QUEUE];
  state.aliases = [];
  state.match = vi.fn().mockResolvedValue({
    id: 'a-9',
    supplier_code: 'CWC605-RL-250',
    product_id: 'p-1',
    product_code: 'SRTWC286-SH',
    product_set_id: null,
    set_code: null,
    set_name: null,
    source: 'manual',
    matched_by: 'manual',
    rebound_stock_rows: 1,
    rebound_invoice_lines: 0,
  });
  state.dismiss = vi.fn().mockResolvedValue({
    id: 'a-8',
    supplier_code: 'CWC605-RL-250',
    product_id: null,
    product_code: null,
    product_set_id: null,
    set_code: null,
    set_name: null,
    source: 'dismissed',
    matched_by: 'dismissed',
    rebound_stock_rows: 1,
    rebound_invoice_lines: 0,
  });
  state.undo = vi.fn((_id: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
  state.rematch = vi.fn();
  state.confirm = vi.fn();
  deferred.inputs.length = 0;
  deferred.run.mockClear();
});

// --------------------------------------------------------------------------- AC-1.1

describe('SupplierCodesTab - the search box (AC-1.1, AC-1.2, AC-1.3)', () => {
  it('narrows the queue to the codes containing what was typed, case-insensitively', () => {
    renderTab();

    typeSearch('cwc605');

    const queue = within(needsCard());
    expect(queue.getByText('CWC605-RL-250')).toBeInTheDocument();
    expect(queue.queryByText('CWC250-SH')).not.toBeInTheDocument();
    expect(queue.queryByText('SRTWT6801-P')).not.toBeInTheDocument();
  });

  it('narrows Remembered by the supplier code OR the code it was matched to', () => {
    state.aliases = [
      alias({ id: 'a-1', supplier_code: 'JBC-CWC605-A', product_code: 'SRTWC286-SH' }),
      alias({ id: 'a-2', supplier_code: 'JBC-9001', product_code: 'CWC605-RL' }),
      alias({ id: 'a-3', supplier_code: 'JBC-7777', product_code: 'SRTWT6801' }),
    ];
    renderTab();

    typeSearch('CWC605');

    const memory = within(rememberedCard());
    // Matched by its own code.
    expect(memory.getByText('JBC-CWC605-A')).toBeInTheDocument();
    // Matched by what it points AT - the buyer types our code as often as theirs.
    expect(memory.getByText('JBC-9001')).toBeInTheDocument();
    expect(memory.queryByText('JBC-7777')).not.toBeInTheDocument();
  });

  it('matches a phrase out of the "Supplier says" text (AC-1.2)', () => {
    renderTab();

    typeSearch('180横排');

    const queue = within(needsCard());
    expect(queue.getByText('CWC605-RL-250')).toBeInTheDocument();
    expect(queue.queryByText('CWC250-SH')).not.toBeInTheDocument();
  });

  it('ANDs two tokens rather than looking for the phrase (AC-1.3)', () => {
    state.rows = [
      row({ item_code: 'CWC605-RL-250', product_name: '连体马桶' }),
      row({ item_code: 'CWC605-RL-180', product_name: '连体马桶' }),
      row({ item_code: 'CWC250-SH', product_name: '挂墙式马桶' }),
    ];
    renderTab();

    typeSearch('CWC 250');

    const queue = within(needsCard());
    expect(queue.getByText('CWC605-RL-250')).toBeInTheDocument();
    expect(queue.getByText('CWC250-SH')).toBeInTheDocument();
    expect(queue.queryByText('CWC605-RL-180')).not.toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- AC-1.4

describe('SupplierCodesTab - the counts while filtering (AC-1.4)', () => {
  it('reads a plain total with the box empty and "n of total" while it is filtering', () => {
    state.aliases = [alias({ id: 'a-1' }), alias({ id: 'a-2', supplier_code: 'CWC605-X' })];
    renderTab();

    expect(screen.getByText('Needs a decision (3)')).toBeInTheDocument();
    expect(screen.getByText('Remembered (2)')).toBeInTheDocument();

    typeSearch('CWC605');

    expect(screen.getByText('Needs a decision (1 of 3)')).toBeInTheDocument();
    expect(screen.getByText('Remembered (1 of 2)')).toBeInTheDocument();
  });

  it('counts decided rows on Confirm regardless of what the filter hides', async () => {
    renderTab();

    const [firstSelect] = screen.getAllByLabelText('Product') as HTMLSelectElement[];
    await waitFor(() =>
      expect(firstSelect.querySelector('option[value="p-1"]')).toBeInTheDocument(),
    );
    fireEvent.change(firstSelect, { target: { value: 'p-1' } });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Confirm (1)' })).not.toBeDisabled(),
    );

    // Filter the decided row OUT of view. What Confirm would move is unchanged.
    typeSearch('SRTWT6801');

    expect(screen.getByRole('button', { name: 'Confirm (1)' })).not.toBeDisabled();
  });
});

// --------------------------------------------------------------------------- AC-1.5

describe('SupplierCodesTab - nothing matches (AC-1.5)', () => {
  it('says so in place of the table, and clearing the box brings every row back', () => {
    state.aliases = [alias()];
    renderTab();

    typeSearch('zzz-nothing-like-this');

    expect(screen.getAllByText('No code matches').length).toBeGreaterThanOrEqual(1);
    expect(within(needsCard()).queryByText('CWC605-RL-250')).not.toBeInTheDocument();
    // Not the "nothing left to answer" state: there IS work, it is merely filtered away.
    expect(screen.queryByText('Every code on file is matched')).not.toBeInTheDocument();

    typeSearch('');

    const queue = within(needsCard());
    expect(queue.getByText('CWC605-RL-250')).toBeInTheDocument();
    expect(queue.getByText('CWC250-SH')).toBeInTheDocument();
    expect(queue.getByText('SRTWT6801-P')).toBeInTheDocument();
    expect(within(rememberedCard()).getByText('SRTWC8357-RL-300')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------- AC-5.1, AC-6.1

describe('SupplierCodesTab - the Remembered table (AC-5.1, AC-6.1)', () => {
  it('shows the matched CODE only, never the code and its name', () => {
    state.aliases = [
      alias({ id: 'a-1', product_code: 'SRTWC8357-300-RL', product_name: 'One piece toilet' }),
    ];
    renderTab();

    const memory = within(rememberedCard());
    expect(memory.getByText('SRTWC8357-300-RL')).toBeInTheDocument();
    expect(memory.queryByText(/SRTWC8357-300-RL - One piece toilet/)).not.toBeInTheDocument();
  });

  it('shows a SET as its set code alone', () => {
    state.aliases = [
      alias({
        id: 'a-1',
        product_code: null,
        product_name: null,
        set_code: 'CWC605-RL',
        set_name: 'Close-coupled WC',
      }),
    ];
    renderTab();

    const memory = within(rememberedCard());
    expect(memory.getByText('CWC605-RL')).toBeInTheDocument();
    expect(memory.queryByText(/CWC605-RL - Close-coupled WC/)).not.toBeInTheDocument();
  });

  it('still says Dismissed for a dismissal, and a dash when a row names neither', () => {
    state.aliases = [
      alias({ id: 'a-1', supplier_code: 'JBC-DISMISSED', source: 'dismissed', product_code: null }),
      alias({
        id: 'a-2',
        supplier_code: 'JBC-NEITHER',
        source: 'manual',
        product_code: null,
        product_name: null,
      }),
    ];
    renderTab();

    const memory = within(rememberedCard());
    // Exactly once: the `How` column printed the same word beside it until S6.
    expect(memory.getAllByText('Dismissed')).toHaveLength(1);
    expect(memory.getAllByText('-').length).toBeGreaterThanOrEqual(1);
  });

  it('carries Code, Matched to, When, By and Forget, and no How column (AC-6.1)', () => {
    state.aliases = [alias()];
    renderTab();

    const memory = within(rememberedCard());
    expect(
      memory.getAllByRole('columnheader').map((h) => h.textContent?.trim()),
    ).toEqual(['Code', 'Matched to', 'When', 'By', 'Forget']);
  });

  it('still forgets a ruling through the deferred countdown', () => {
    state.aliases = [alias()];
    renderTab();

    fireEvent.click(within(rememberedCard()).getByRole('button', { name: 'Forget' }));

    expect(deferred.run).toHaveBeenCalledWith({ id: 'a-1', subject: 'SRTWC8357-RL-300' });
    expect(deferred.inputs.some((i) => i.actionKey === 'supplier_code_alias.forget')).toBe(
      true,
    );
  });
});
