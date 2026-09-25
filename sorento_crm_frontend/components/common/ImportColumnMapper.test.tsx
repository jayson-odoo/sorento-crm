/**
 * The shared inline column mapper (V1/V2, fix-round review R1,
 * PLAN-import-column-mapper-24sep.md F1) - tested directly, against a probe the caller
 * already has, rather than through either upload dialog: what is asserted here is the
 * mapper's OWN contract (R3/R5/AC-M2/AC-M7/AC-M9/AC-M11/AC-M12/AC-M16), independent of
 * which dialog happens to be hosting it.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

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

import {
  ImportColumnMapper,
  IGNORE_FIELD,
  type ImportMappingColumn,
  type ImportMappingField,
  type ImportMappingHeaderField,
  type ImportMappingProbe,
} from './ImportColumnMapper';

const FIELDS: ImportMappingField[] = [
  { field: 'item_code', label: 'Item code' },
  { field: 'qty', label: 'Quantity' },
];

/** What production actually sends for a doc type carrying every header-block field
 *  (proforma_invoice) - the default so the two pre-existing header-field tests below
 *  exercise the REAL choice list rather than an empty one, now that the component reads
 *  `probe.header_field_choices` instead of its own hard-coded constant (V2). */
const DEFAULT_HEADER_FIELD_CHOICES: ImportMappingField[] = [
  { field: 'pi_number', label: 'PI number' },
  { field: 'invoice_date', label: 'Invoice date' },
  { field: 'bl_no', label: 'BL' },
  { field: 'container_no', label: 'Container' },
  { field: 'seal_no', label: 'Seal' },
  { field: 'currency', label: 'Currency' },
];

function probeWith(
  columns: ImportMappingColumn[],
  headerRow: number | null = 1,
  headerFields?: ImportMappingHeaderField[],
  headerFieldChoices: ImportMappingField[] = DEFAULT_HEADER_FIELD_CHOICES,
): ImportMappingProbe {
  return {
    header_row: headerRow,
    columns,
    required_fields: ['item_code', 'qty'],
    ...(headerFields ? { header_fields: headerFields } : {}),
    header_field_choices: headerFieldChoices,
  };
}

function renderMapper(probe: ImportMappingProbe) {
  const onChange = vi.fn();
  const onHeaderRowChange = vi.fn();
  const view = render(
    <ImportColumnMapper
      probe={probe}
      fields={FIELDS}
      onChange={onChange}
      onHeaderRowChange={onHeaderRowChange}
    />,
  );
  return { ...view, onChange, onHeaderRowChange };
}

/** Open a SearchableSelect trigger - same two-event pattern the sibling dialog specs use. */
function openSelect(trigger: HTMLElement) {
  fireEvent.pointerDown(trigger, { button: 0 });
  fireEvent.click(trigger);
}

describe('ImportColumnMapper', () => {
  it('renders ONE sample value (no joiner) and the header text with its own line break kept (R5, owner override 24 Sep evening)', () => {
    // RTL's default text/title matchers COLLAPSE whitespace (including a newline) before
    // comparing, which would hide the exact bug this test exists to catch - reading the
    // raw DOM node's `textContent` directly (never normalised) instead.
    const { container } = renderMapper(
      probeWith([
        { position: 0, header: '件数\n（件）', samples: ['120'], field: null, source: 'none' },
      ]),
    );

    expect(screen.getByText('120')).toBeInTheDocument();
    // No " · " joiner between two values - the mapper shows ONE sample per column now.
    expect(screen.queryByText(/120 · /)).toBeNull();
    const headerNode = container.querySelector('.whitespace-pre-line');
    expect(headerNode?.textContent).toBe('件数\n（件）');
  });

  it('offers Ignore in the field select (G2/AC-M7)', () => {
    renderMapper(
      probeWith([{ position: 0, header: 'A', samples: [], field: null, source: 'none' }]),
    );

    openSelect(screen.getByRole('combobox'));
    expect(screen.getByText('Ignore')).toBeInTheDocument();
  });

  it('flags a required column with no current pick (AC-M9)', () => {
    renderMapper(
      probeWith([
        { position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' },
        { position: 1, header: 'QTY', samples: [], field: null, source: 'none' },
      ]),
    );

    expect(screen.getByText('Still needed: Quantity')).toBeInTheDocument();
  });

  it('collapses when every column already has a field or ignore (AC-M11)', () => {
    renderMapper(
      probeWith([
        { position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' },
        { position: 1, header: 'SKIP', samples: [], field: IGNORE_FIELD, source: 'supplier' },
      ]),
    );

    expect(
      screen.getByText('2 of 2 columns mapped from saved layout'),
    ).toBeInTheDocument();
  });

  it('expands with the never-seen column highlighted when one is unresolved (AC-M12)', () => {
    renderMapper(
      probeWith([
        { position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' },
        { position: 1, header: 'NEWCOL', samples: [], field: null, source: 'none' },
      ]),
    );

    // Expanded (not the collapsed "N of N" summary): both rows are on screen.
    expect(screen.getByTitle('ITEM')).toBeInTheDocument();
    const newRow = screen.getByTitle('NEWCOL').parentElement as HTMLElement;
    expect(newRow.className).toContain('bg-primary/5');
    const knownRow = screen.getByTitle('ITEM').parentElement as HTMLElement;
    expect(knownRow.className).not.toContain('bg-primary/5');
  });

  it('drops the highlight once the never-seen column has a pick', () => {
    renderMapper(
      probeWith([{ position: 0, header: 'NEWCOL', samples: [], field: null, source: 'none' }]),
    );

    const row = screen.getByTitle('NEWCOL').parentElement as HTMLElement;
    expect(row.className).toContain('bg-primary/5');

    openSelect(screen.getByRole('combobox'));
    fireEvent.click(screen.getByText('Item code'));

    // The highlight means "you have never decided this one" - once decided, in THIS same
    // session, it must stop standing out from the columns already known before the file
    // landed. The component today keys the highlight off the probe's own immutable
    // `source`, not the operator's live pick, so this reads as unresolved even after the
    // operator has just resolved it.
    expect(row.className).not.toContain('bg-primary/5');
  });

  it('says "No header row was found." with no second, explanatory sentence (AC-M16)', () => {
    renderMapper(probeWith([], null));

    const node = screen.getByText(/No header row was found/);
    expect(node.textContent?.trim()).toBe('No header row was found.');
  });

  // ------------------------------------------------------------------- //
  // Header fields section (F1/F2, PLAN-pi-header-fields-convert-fixes-24sep.md, R-D)
  // ------------------------------------------------------------------- //

  it('renders a header-field row with its sample and exactly the six block fields plus Ignore', () => {
    renderMapper(
      probeWith(
        [{ position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' }],
        14,
        [{ row: 13, label: '提单号', sample: 'OOLU2339207730', field: null, source: 'none' }],
      ),
    );

    expect(screen.getByText('Header fields')).toBeInTheDocument();
    expect(screen.getByTitle('提单号')).toBeInTheDocument();
    expect(screen.getByTitle('OOLU2339207730')).toBeInTheDocument();

    const selects = screen.getAllByRole('combobox');
    // The LAST combobox on screen is the header field's own (the column section renders
    // first) - open it and check its exact option set.
    openSelect(selects[selects.length - 1]);
    for (const label of [
      'Ignore',
      'PI number',
      'Invoice date',
      'BL',
      'Container',
      'Seal',
      'Currency',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // Consignee is never offered (R-B).
    expect(screen.queryByText('Consignee')).toBeNull();
  });

  it('folds the header fields section when every pair already resolves (F2: same fold rule as columns)', () => {
    renderMapper(
      probeWith(
        [{ position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' }],
        14,
        [
          { row: 13, label: '提单号', sample: 'OOLU2339207730', field: 'bl_no', source: 'supplier' },
          { row: 13, label: '柜号', sample: 'FSCU9304169', field: 'container_no', source: 'supplier' },
        ],
      ),
    );

    expect(
      screen.getByText('2 of 2 header fields mapped from saved layout'),
    ).toBeInTheDocument();
    // Folded: the individual label rows are not on screen.
    expect(screen.queryByTitle('提单号')).toBeNull();
  });

  it('opens the header fields section when one label is unknown', () => {
    renderMapper(
      probeWith(
        [{ position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' }],
        14,
        [
          { row: 13, label: '提单号', sample: 'OOLU2339207730', field: 'bl_no', source: 'supplier' },
          { row: 13, label: '柜号', sample: 'FSCU9304169', field: null, source: 'none' },
        ],
      ),
    );

    expect(screen.queryByText(/header fields mapped from saved layout/)).toBeNull();
    expect(screen.getByTitle('柜号')).toBeInTheDocument();
  });

  it('emitChange (onChange) includes a header-field pick with the label as `header`', () => {
    const { onChange } = renderMapper(
      probeWith(
        [{ position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' }],
        14,
        [{ row: 13, label: '柜号', sample: 'FSCU9304169', field: null, source: 'none' }],
      ),
    );
    onChange.mockClear();

    const selects = screen.getAllByRole('combobox');
    openSelect(selects[selects.length - 1]);
    fireEvent.click(screen.getByText('Container'));

    expect(onChange).toHaveBeenCalledWith(
      expect.arrayContaining([{ header: '柜号', field: 'container_no' }]),
    );
  });

  it('V2 (fix round 1, PLAN-pi-header-fields-convert-fixes-24sep-fixes-24sep.md): offers only the field choices the probe itself states, not a hard-coded superset', () => {
    // A packing-list-only probe's own block fields (`packing_list_reader._BLOCK_FIELDS`)
    // carry no `currency` at all - Currency is a proforma-invoice-only concept. The
    // mapper's `HEADER_FIELD_CHOICES` constant is fixed regardless of doc type today, so
    // a packing-list upload's "Header fields" section still offers Currency, which no
    // reader for that doc type will ever save.
    const probe = {
      ...probeWith(
        [{ position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' }],
        14,
        [{ row: 13, label: '货柜号', sample: 'FSCU9304169', field: null, source: 'none' }],
      ),
      header_field_choices: [
        { field: 'pi_number', label: 'PI number' },
        { field: 'invoice_date', label: 'Invoice date' },
        { field: 'bl_no', label: 'BL' },
        { field: 'container_no', label: 'Container' },
        { field: 'seal_no', label: 'Seal' },
      ],
    } as ImportMappingProbe;
    renderMapper(probe);

    const selects = screen.getAllByRole('combobox');
    openSelect(selects[selects.length - 1]);
    expect(screen.queryByText('Currency')).toBeNull();
  });

  it('renders the "Header fields" section ABOVE the columns grid, not below it', () => {
    // The header block (BL/container/seal, often the FIRST thing a purchasing user
    // recognises on the sheet) is what the operator reads first - the columns grid is
    // long (DAFUYUAN alone has two dozen columns) and would otherwise push "Header
    // fields" out of view below it, making an operator scroll past every column just to
    // reach the three-field block they actually came to check.
    renderMapper(
      probeWith(
        // Unresolved (`field: null`) so the columns section stays EXPANDED (the row-list
        // shape, not the collapsed "N of N mapped" summary) and its own "ITEM" row
        // actually renders onto the DOM this test inspects.
        [{ position: 0, header: 'ITEM', samples: [], field: null, source: 'none' }],
        14,
        [{ row: 13, label: '提单号', sample: 'OOLU2339207730', field: null, source: 'none' }],
      ),
    );

    const headerFieldsHeading = screen.getByText('Header fields');
    const columnRow = screen.getByTitle('ITEM');

    // `DOCUMENT_POSITION_FOLLOWING` (4) set on the result means `columnRow` comes AFTER
    // `headerFieldsHeading` in document order - i.e. the heading precedes the columns.
    const position = headerFieldsHeading.compareDocumentPosition(columnRow);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders "Header fields" then "Line fields" section titles, with the header-row stepper living in the Line fields title row', () => {
    // Two named sections, in reading order: the document-level facts (Header fields)
    // first, then the per-line columns table - which needs its own title now that it
    // sits below a named sibling section rather than being the mapper's only content.
    // The "Header row N" stepper answers "which row is the COLUMN header", so it moves
    // into the Line fields section's own title row rather than floating above both
    // sections the way it does today.
    renderMapper(
      probeWith(
        [{ position: 0, header: 'ITEM', samples: [], field: null, source: 'none' }],
        14,
        [{ row: 13, label: '提单号', sample: 'OOLU2339207730', field: null, source: 'none' }],
      ),
    );

    const headerFieldsHeading = screen.getByText('Header fields');
    // RED today: no "Line fields" title exists anywhere on the mapper - this throws
    // before the rest of the test can run, which is itself the failure this test
    // exists to catch.
    const lineFieldsHeading = screen.getByText('Line fields');

    const order = headerFieldsHeading.compareDocumentPosition(lineFieldsHeading);
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const stepper = screen.getByText(/Header row/);
    const lineFieldsSection = lineFieldsHeading.closest('div') as HTMLElement;
    const headerFieldsSection = headerFieldsHeading.closest('div') as HTMLElement;
    expect(lineFieldsSection.contains(stepper)).toBe(true);
    expect(headerFieldsSection.contains(stepper)).toBe(false);
  });

  it('V-SO (owner ruling, 25 Sep): a probe that lists so_no as a header-field choice renders "SO"', () => {
    // SO is now its own header-block field (`so_no`), distinct from BL - a probe that
    // states it among `header_field_choices` (the mapper's own field vocabulary, V2)
    // must offer "SO" in the field select the same way it already offers BL/Container/
    // Seal/PI number/Invoice date/Currency.
    const probe = {
      ...probeWith(
        [{ position: 0, header: 'ITEM', samples: [], field: 'item_code', source: 'supplier' }],
        14,
        [{ row: 13, label: '客户SO', sample: 'SO456', field: null, source: 'none' }],
      ),
      header_field_choices: [
        { field: 'so_no', label: 'SO' },
        { field: 'bl_no', label: 'BL' },
        { field: 'container_no', label: 'Container' },
      ],
    } as ImportMappingProbe;
    renderMapper(probe);

    const selects = screen.getAllByRole('combobox');
    openSelect(selects[selects.length - 1]);
    expect(screen.getByText('SO')).toBeInTheDocument();
  });
});
