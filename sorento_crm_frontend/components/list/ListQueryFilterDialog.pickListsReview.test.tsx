/**
 * FILTER-MULTISELECT PR7 review: the single pick list (`eq` / `ne` on an option_source field) searches the server
 * and pages like the multi one (loader called with a query and pageIndex 1), and a saved `eq` value that is not on
 * page one reopens showing a label, never the placeholder and never the id.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const FIELDS = [
  {
    field_key: 'category_id', label: 'Category', data_type: 'uuid', compile_key: 'product.category_id',
    allowed_operators: ['eq', 'in'], filterable: true, exportable: true, is_line_field: false, sort_order: 1,
    filter_ui_type: 'foreign_key', option_source: { kind: 'distinct' },
  },
  {
    field_key: 'product_name', label: 'Name', data_type: 'string', compile_key: 'product.product_name',
    allowed_operators: ['eq', 'in'], filterable: true, exportable: true, is_line_field: false, sort_order: 2,
    filter_ui_type: 'text', option_source: null,
  },
];
const fetchListQueryFieldOptions = vi.hoisted(() => vi.fn());
vi.mock('@/lib/list-query/listQueryService', () => ({
  fetchListQueryFields: vi.fn(async () => FIELDS),
  fetchListQueryFieldOptions: (...args: unknown[]) => fetchListQueryFieldOptions(...args),
}));

const singleProps = vi.hoisted(() => [] as Record<string, unknown>[]);
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string; options?: { value: string; label: string }[]; placeholder?: string;
    selectedOption?: { value: string; label: string }; fetchOptions?: unknown; paginated?: boolean;
  }) => {
    singleProps.push(props as Record<string, unknown>);
    const found = [...(props.options ?? []), ...(props.selectedOption ? [props.selectedOption] : [])].find(
      (o) => o.value === props.value,
    );
    return (
      <div data-testid="single" data-field={props.placeholder}>
        <span data-testid={props.placeholder === 'Choose a value' ? 'single-shown' : 'other-shown'}>{found ? found.label : props.placeholder}</span>
        {(props.options ?? []).map((o) => <i key={o.value}>{o.label}</i>)}
      </div>
    );
  },
}));
import { ListQueryFilterDialog } from './ListQueryFilterDialog';

const A = '11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const B = '22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

function renderDialog(initialFilter: unknown) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ListQueryFilterDialog resourceKey={'products' as never} open onOpenChange={vi.fn()} initialFilter={initialFilter as never} onApply={vi.fn()} />
    </QueryClientProvider>,
  );
}
const cond = (op: string, value: unknown) => ({ op: 'and', children: [{ field_key: 'category_id', op, value }] });
const latest = () => singleProps.filter((p) => p.placeholder === 'Choose a value').at(-1);

beforeEach(() => {
  vi.clearAllMocks();
  singleProps.length = 0;
  fetchListQueryFieldOptions.mockImplementation(async (_r: string, _f: string, p: { query?: string; page?: number }) => {
    const plainFirstPage = (p.page ?? 1) === 1 && !p.query;
    return plainFirstPage
      ? { data: [{ value: B, label: 'ZZT Beta' }], pagination: { total: 2, page: 1, limit: 50 } }
      : { data: [{ value: A, label: 'ZZT Alpha' }], pagination: { total: 2, page: 2, limit: 50 } };
  });
});

describe('Advanced filter dialog - the single pick list', () => {
  it('is a paginated server search, like the multi one', async () => {
    renderDialog(cond('eq', ''));
    await waitFor(() => expect(typeof latest()?.fetchOptions).toBe('function'));
    expect(latest().paginated).toBe(true);
  });

  it('its loader sends the query and the next page to the options endpoint', async () => {
    renderDialog(cond('eq', ''));
    await waitFor(() => expect(typeof latest()?.fetchOptions).toBe('function'));
    await (latest().fetchOptions as (q: string, p: number) => Promise<unknown>)('Alp', 1);
    expect(fetchListQueryFieldOptions).toHaveBeenCalledWith('products', 'category_id', expect.objectContaining({ query: 'Alp', page: 2 }));
  });

  it('a saved eq value that is not on page one reopens showing a label, not the placeholder, never the id', async () => {
    renderDialog(cond('eq', A));
    const shown = await screen.findByTestId('single-shown');
    await waitFor(() => expect(shown.textContent).not.toBe('Choose a value'));
    expect(shown.textContent).not.toContain(A);
    expect(screen.queryByText(new RegExp(A))).toBeNull();
  });
});
