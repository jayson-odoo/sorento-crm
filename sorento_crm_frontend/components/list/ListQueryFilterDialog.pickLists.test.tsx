/**
 * FILTER-MULTISELECT PR7 (design 4.1): the Advanced filter dialog's pick lists. A field with `option_source` and
 * operator `in` is a multi control whose options come from the options endpoint (service mocked); `eq` is a single
 * select; a field without `option_source` keeps the text box; a saved `in: [a, b]` reopens with both picked and no id
 * shown. The service function name `fetchListQueryFieldOptions(resource, fieldKey, { query, page })` is this file's
 * assumption of the contract.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ value, onChange, options, placeholder }: {
    value?: string; onChange: (v: string) => void; options?: { value: string; label: string }[]; placeholder?: string;
  }) => (
    <select aria-label={placeholder ?? 'select'} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
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


import { ListQueryFilterDialog } from './ListQueryFilterDialog';

const A = '11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const B = '22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

function renderDialog(initialFilter: unknown, onApply = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ListQueryFilterDialog
        resourceKey={'products' as never}
        open
        onOpenChange={vi.fn()}
        initialFilter={initialFilter as never}
        onApply={onApply}
      />
    </QueryClientProvider>,
  );
  return onApply;
}
const cond = (op: string, value: unknown, field = 'category_id') => ({ op: 'and', children: [{ field_key: field, op, value }] });
const selectsWith = (value: string) =>
  screen.queryAllByRole('combobox').concat(screen.queryAllByRole('listbox')).filter((el) =>
    el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function control(value: string) {
  await waitFor(() => {
    if (!selectsWith(value).length) throw new Error(`no control offering option "${value}"`);
  });
  return selectsWith(value)[0];
}
const applied = (onApply: ReturnType<typeof vi.fn>) =>
  (onApply.mock.calls.at(-1)?.[0] as { children: { field_key: string; op: string; value: unknown }[] }).children[0];

beforeEach(() => {
  vi.clearAllMocks();
  fetchListQueryFieldOptions.mockResolvedValue({
    data: [{ value: A, label: 'ZZT Alpha' }, { value: B, label: 'ZZT Beta' }],
    pagination: { total: 2, page: 1, limit: 50 },
  });
});

describe('Advanced filter dialog - pick lists', () => {
  it('an in condition on an option_source field is a multi control fed by the options endpoint', async () => {
    renderDialog(cond('in', []));
    const el = await control(A);
    expect(el.hasAttribute('multiple')).toBe(true);
    expect(fetchListQueryFieldOptions).toHaveBeenCalledWith('products', 'category_id', expect.anything());
  });

  it('picking two writes an array into the condition sent on Apply', async () => {
    const user = userEvent.setup();
    const onApply = renderDialog(cond('in', []));
    await user.selectOptions(await control(A), [A, B]);
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect([...(applied(onApply).value as string[])].sort()).toEqual([A, B]);
    expect(applied(onApply).op).toBe('in');
  });

  it('an eq condition on an option_source field is a single select', async () => {
    const user = userEvent.setup();
    const onApply = renderDialog(cond('eq', ''));
    const el = await control(A);
    expect(el.hasAttribute('multiple')).toBe(false);
    await user.selectOptions(el, A);
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(applied(onApply).value).toBe(A);
  });

  it('a field without option_source keeps the text box and never asks for options', async () => {
    renderDialog(cond('eq', '', 'product_name'));
    expect(await screen.findByPlaceholderText('Value')).toBeInTheDocument();
    expect(fetchListQueryFieldOptions).not.toHaveBeenCalled();
  });

  it('an existing in: [a, b] reopens with both picked by label and no id shown', async () => {
    renderDialog(cond('in', [A, B]));
    const el = await control(A);
    await waitFor(() =>
      expect(Array.from(el.selectedOptions).map((o) => o.textContent).sort()).toEqual(['ZZT Alpha', 'ZZT Beta']),
    );
    expect(screen.queryByDisplayValue(new RegExp(A))).toBeNull();
    expect(screen.queryByText(new RegExp(A))).toBeNull();
  });
});
