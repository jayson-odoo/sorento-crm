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

function probeWith(
  columns: ImportMappingColumn[],
  headerRow: number | null = 1,
  headerFields?: ImportMappingHeaderField[],
): ImportMappingProbe {
  return {
    header_row: headerRow,
    columns,
    required_fields: ['item_code', 'qty'],
    ...(headerFields ? { header_fields: headerFields } : {}),
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
});
