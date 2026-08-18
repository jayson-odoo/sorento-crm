/**
 * ProductDiscontinuedScopeEditor (AC-14, AC-18).
 *
 * SearchableSelect / SearchableMultiSelect are stubbed as deterministic native
 * controls (same technique as RunPlanningModal.test.tsx) so a pick is a plain
 * fireEvent, not a Radix popover interaction. The brands hook is stubbed too -
 * this is a component test, not an integration test of the query layer.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    disabled,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string; disabled?: boolean }[];
    disabled?: boolean;
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    disabled,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options: { value: string; label: string }[];
    disabled?: boolean;
    placeholder?: string;
  }) => (
    <div
      data-testid="brand-multiselect"
      data-placeholder={placeholder ?? 'multi-select'}
      aria-disabled={disabled}
    >
      {options.map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            aria-label={o.label}
            checked={value.includes(o.value)}
            disabled={disabled}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...value, o.value]
                  : value.filter((x) => x !== o.value),
              )
            }
          />
          {o.label}
        </label>
      ))}
      {/* The real control's Select-all affordance, which acts on every loaded option. */}
      <button
        type="button"
        data-testid="brand-select-all"
        disabled={disabled}
        onClick={() => onChange(options.map((o) => o.value))}
      >
        Select all
      </button>
    </div>
  ),
}));

const brandsHook = vi.fn();
vi.mock('../../hooks/use-product-discontinued-scope-brands', () => ({
  useProductDiscontinuedScopeBrands: (companyId: string | null) => brandsHook(companyId),
}));

import ProductDiscontinuedScopeEditor from './product-discontinued-scope-editor';
import { createAllScopeRow, type ScopeRow } from '../../lib/productDiscontinuedScopes';

const COMPANIES = [
  { id: 'co-1', name: 'Sorento', code: 'SRT' },
  { id: 'co-2', name: 'Mocha', code: 'MCH' },
];

beforeEach(() => {
  brandsHook.mockReset();
  brandsHook.mockReturnValue({
    data: [
      { id: 'br-1', brand_code: 'MOCHA', brand_name: 'Mocha' },
      { id: 'br-2', brand_code: 'NOVA', brand_name: 'Nova' },
    ],
    isLoading: false,
    isError: false,
  });
});

function renderEditor(
  rows: ScopeRow[],
  onChange = vi.fn(),
  onBrandsLoadErrorChange = vi.fn(),
) {
  render(
    <ProductDiscontinuedScopeEditor
      rows={rows}
      companies={COMPANIES}
      onChange={onChange}
      onBrandsLoadErrorChange={onBrandsLoadErrorChange}
    />,
  );
  return { onChange, onBrandsLoadErrorChange };
}

describe('ProductDiscontinuedScopeEditor - empty state', () => {
  it('shows the no-scope hint and no rows when there are zero rows', () => {
    renderEditor([]);
    expect(
      screen.getByText(/will not be notified about any discontinued product/i),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  });
});

describe('ProductDiscontinuedScopeEditor - populated state', () => {
  it('renders one company select + one brand multi-select per row', () => {
    const rows: ScopeRow[] = [
      {
        key: 'k1',
        companyId: 'co-1',
        companyName: 'Sorento',
        brandIds: ['br-1'],
        brandLabels: { 'br-1': 'Mocha' },
      },
    ];
    renderEditor(rows);
    expect(screen.getByLabelText('Select a company')).toBeInTheDocument();
    expect(screen.getByLabelText('Mocha')).toBeChecked();
    expect(screen.getByLabelText('Nova')).not.toBeChecked();
  });

  it('does not pre-populate the no-scope hint when rows exist', () => {
    renderEditor([createAllScopeRow()]);
    expect(
      screen.queryByText(/will not be notified about any discontinued product/i),
    ).not.toBeInTheDocument();
  });
});

describe('ProductDiscontinuedScopeEditor - all-companies locks the brand select', () => {
  it('disables the brand multi-select when the row is all-companies', () => {
    renderEditor([createAllScopeRow()]);
    const brandGroup = screen.getByTestId('brand-multiselect');
    expect(brandGroup).toHaveAttribute('aria-disabled', 'true');
  });

  it('the brand select is enabled once a specific company is chosen', () => {
    const rows: ScopeRow[] = [
      { key: 'k1', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
    ];
    renderEditor(rows);
    const brandGroup = screen.getByTestId('brand-multiselect');
    expect(brandGroup).toHaveAttribute('aria-disabled', 'false');
  });

  it('switching the company back to All companies clears any picked brands and re-locks', () => {
    const rows: ScopeRow[] = [
      {
        key: 'k1',
        companyId: 'co-1',
        companyName: 'Sorento',
        brandIds: ['br-1'],
        brandLabels: { 'br-1': 'Mocha' },
      },
    ];
    const { onChange } = renderEditor(rows);
    fireEvent.change(screen.getByLabelText('Select a company'), {
      target: { value: '__all_companies__' },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ companyId: null, brandIds: [], brandLabels: {} }),
    ]);
  });
});

describe('ProductDiscontinuedScopeEditor - a company already used elsewhere is disabled', () => {
  it('disables a taken company option on the OTHER row, but not on its own row', () => {
    const rows: ScopeRow[] = [
      { key: 'k1', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
      { key: 'k2', companyId: 'co-2', companyName: 'Mocha', brandIds: [], brandLabels: {} },
    ];
    renderEditor(rows);
    const selects = screen.getAllByLabelText('Select a company') as HTMLSelectElement[];
    // Row 1 (Sorento): Sorento's own option must stay pickable (not disabled),
    // Mocha (taken by row 2) must be disabled.
    const row1Sorento = Array.from(selects[0].options).find((o) => o.value === 'co-1')!;
    const row1Mocha = Array.from(selects[0].options).find((o) => o.value === 'co-2')!;
    expect(row1Sorento.disabled).toBe(false);
    expect(row1Mocha.disabled).toBe(true);
  });

  it('disables "All companies" everywhere once one row already uses it', () => {
    const rows: ScopeRow[] = [
      createAllScopeRow(),
      { key: 'k2', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
    ];
    renderEditor(rows);
    const selects = screen.getAllByLabelText('Select a company') as HTMLSelectElement[];
    const row2AllCompanies = Array.from(selects[1].options).find(
      (o) => o.value === '__all_companies__',
    )!;
    expect(row2AllCompanies.disabled).toBe(true);
    // The row that already IS all-companies keeps its own option pickable.
    const row1AllCompanies = Array.from(selects[0].options).find(
      (o) => o.value === '__all_companies__',
    )!;
    expect(row1AllCompanies.disabled).toBe(false);
  });
});

describe('ProductDiscontinuedScopeEditor - a saved company outside the admin grants', () => {
  it('renders the saved company by name instead of a blank select', () => {
    // The option list comes from the acting admin's own company grants, but the
    // scope being edited can name a company they were never granted. Without the
    // merge the select has no matching option and shows blank, while the read view
    // two panels away shows the name - which reads as the value having been lost.
    const rows: ScopeRow[] = [
      {
        key: 'k1',
        companyId: 'co-9',
        companyName: 'Ungranted Co',
        brandIds: [],
        brandLabels: {},
      },
    ];
    renderEditor(rows);

    const select = screen.getByLabelText('Select a company') as HTMLSelectElement;
    expect(select.value).toBe('co-9');
    const option = Array.from(select.options).find((o) => o.value === 'co-9');
    expect(option?.textContent).toBe('Ungranted Co');
  });

  it('the merged company counts as taken, so another row cannot claim it', () => {
    const rows: ScopeRow[] = [
      {
        key: 'k1',
        companyId: 'co-9',
        companyName: 'Ungranted Co',
        brandIds: [],
        brandLabels: {},
      },
      { key: 'k2', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
    ];
    renderEditor(rows);

    const selects = screen.getAllByLabelText('Select a company') as HTMLSelectElement[];
    const row2Ungranted = Array.from(selects[1].options).find((o) => o.value === 'co-9')!;
    expect(row2Ungranted.disabled).toBe(true);
  });
});

describe('ProductDiscontinuedScopeEditor - add / remove row', () => {
  it('"Add scope" appends an all-companies row when none is taken yet', () => {
    const { onChange } = renderEditor([]);
    fireEvent.click(screen.getByRole('button', { name: /add scope/i }));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ companyId: null, brandIds: [] }),
    ]);
  });

  it('"Add scope" starts on the first free company once all-companies is taken', () => {
    const rows: ScopeRow[] = [createAllScopeRow()];
    const { onChange } = renderEditor(rows);
    fireEvent.click(screen.getByRole('button', { name: /add scope/i }));
    const [calledWith] = onChange.mock.calls[0];
    expect(calledWith).toHaveLength(2);
    expect(calledWith[1]).toMatchObject({ companyId: 'co-1', companyName: 'Sorento' });
  });

  it('"Add scope" is disabled once all-companies AND every company are taken', () => {
    // There is nothing left for a new row to mean, and appending a second
    // all-companies row would be a duplicate the backend then dedupes away.
    const rows: ScopeRow[] = [
      createAllScopeRow(),
      { key: 'k2', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
      { key: 'k3', companyId: 'co-2', companyName: 'Mocha', brandIds: [], brandLabels: {} },
    ];
    const { onChange } = renderEditor(rows);
    const addButton = screen.getByRole('button', { name: /add scope/i });

    expect(addButton).toBeDisabled();
    fireEvent.click(addButton);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('removing the only row clears the list back to empty (re-shows the hint on re-render)', () => {
    const rows: ScopeRow[] = [createAllScopeRow()];
    const { onChange } = renderEditor(rows);
    fireEvent.click(screen.getByLabelText('Remove scope'));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('removing one of two rows leaves only the other', () => {
    const rows: ScopeRow[] = [
      { key: 'k1', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
      { key: 'k2', companyId: 'co-2', companyName: 'Mocha', brandIds: [], brandLabels: {} },
    ];
    const { onChange } = renderEditor(rows);
    const removeButtons = screen.getAllByLabelText('Remove scope');
    fireEvent.click(removeButtons[0]);
    expect(onChange).toHaveBeenCalledWith([rows[1]]);
  });
});


describe('ProductDiscontinuedScopeEditor - no brand picked means all brands', () => {
  const companyRow = (brandIds: string[]): ScopeRow[] => [
    {
      key: 'k1',
      companyId: 'co-1',
      companyName: 'Sorento',
      brandIds,
      brandLabels: Object.fromEntries(brandIds.map((id) => [id, id])),
    },
  ];

  it('offers only the company\'s own brands, with all-brands as the empty state', () => {
    renderEditor(companyRow([]));
    expect(screen.getByLabelText('Mocha')).not.toBeChecked();
    expect(screen.getByLabelText('Nova')).not.toBeChecked();
    // No extra option to click for "all": an empty pick already means all brands,
    // which the trigger says in place of a chip.
    expect(screen.queryByLabelText('All brands')).not.toBeInTheDocument();
    expect(screen.getByTestId('brand-multiselect')).toHaveAttribute(
      'data-placeholder',
      'All brands',
    );
  });

  it('clearing the last brand leaves the row on all brands (empty brandIds)', () => {
    const { onChange } = renderEditor(companyRow(['br-1']));
    fireEvent.click(screen.getByLabelText('Mocha'));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ companyId: 'co-1', brandIds: [], brandLabels: {} }),
    ]);
  });

  it('Select all picks every loaded brand rather than collapsing to all-brands', () => {
    const { onChange } = renderEditor(companyRow([]));
    fireEvent.click(screen.getByTestId('brand-select-all'));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        companyId: 'co-1',
        brandIds: ['br-1', 'br-2'],
        brandLabels: { 'br-1': 'Mocha', 'br-2': 'Nova' },
      }),
    ]);
  });
});

describe('ProductDiscontinuedScopeEditor - the brand load failed', () => {
  beforeEach(() => {
    brandsHook.mockReturnValue({ data: undefined, isLoading: false, isError: true });
  });

  it('says so and disables the picker, so an empty list is not read as all brands', () => {
    renderEditor([
      { key: 'k1', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
    ]);
    expect(screen.getByRole('alert')).toHaveTextContent(/brands could not be loaded/i);
    expect(screen.getByTestId('brand-multiselect')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByTestId('brand-select-all')).toBeDisabled();
  });

  it('marks the row so it cannot be saved as all brands, without dirtying the scopes', () => {
    const { onChange, onBrandsLoadErrorChange } = renderEditor([
      { key: 'k1', companyId: 'co-1', companyName: 'Sorento', brandIds: [], brandLabels: {} },
    ]);
    expect(onBrandsLoadErrorChange).toHaveBeenCalledWith([
      expect.objectContaining({ companyId: 'co-1', brandsLoadError: true }),
    ]);
    // A failed fetch is not an edit: it must not make the dialog send scopes.
    expect(onChange).not.toHaveBeenCalled();
  });

  it('tells the row it is unsavable while nothing is picked', () => {
    renderEditor([
      {
        key: 'k1',
        companyId: 'co-1',
        companyName: 'Sorento',
        brandIds: [],
        brandLabels: {},
        brandsLoadError: true,
      },
    ]);
    expect(screen.getByRole('alert')).toHaveTextContent(/remove this row to save/i);
  });

  it('a row that still has its saved brands is savable, so it keeps the plain message', () => {
    renderEditor([
      {
        key: 'k1',
        companyId: 'co-1',
        companyName: 'Sorento',
        brandIds: ['br-1'],
        brandLabels: { 'br-1': 'Mocha' },
        brandsLoadError: true,
      },
    ]);
    expect(screen.getByRole('alert')).not.toHaveTextContent(/remove this row/i);
  });

  it('keeps the brands already saved on the row visible while the load is broken', () => {
    renderEditor([
      {
        key: 'k1',
        companyId: 'co-1',
        companyName: 'Sorento',
        brandIds: ['br-1'],
        brandLabels: { 'br-1': 'Mocha' },
      },
    ]);
    expect(screen.getByLabelText('Mocha')).toBeChecked();
  });
});
