/**
 * The editable spec table - AC-A.1, A.1b, A.2, A.4, A.5, A.14, A.6, C.1, C.2, C.4.
 *
 * `DataGridTable` DOES mount rows under jsdom, but `DataGrid` calls
 * `useListingColumnPreferences` and renders skeletons until it answers - and under
 * jsdom nothing answers. Mocking it is what makes rows, badges and per-row buttons
 * assertable (see CLAUDE.md).
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { SpecTable } from './SpecTable';
import { buildSpecTableRows } from './specTableModel';
import { statusPillClass } from '@/lib/status-pill';
import {
  MOCK_EXCEPTIONS,
  MOCK_PROVENANCE,
  MOCK_REGISTRY,
  MOCK_VALUES,
} from './__mocks__/specTable.fixtures';

/**
 * `fireEvent`, not `user-event`: the latter is not a dependency of this repo and the
 * existing component tests all drive the DOM this way.
 */
function clearInput(input: HTMLElement) {
  fireEvent.change(input, { target: { value: '' } });
}

function typeInto(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
}

/**
 * Radix opens a dropdown on pointerdown, which `fireEvent.click` alone does not send.
 */
function openMenu(trigger: HTMLElement) {
  fireEvent.pointerDown(
    trigger,
    new PointerEvent('pointerdown', { bubbles: true, button: 0, ctrlKey: false }),
  );
  fireEvent.click(trigger);
}

function rows() {
  return buildSpecTableRows({
    values: MOCK_VALUES,
    provenance: MOCK_PROVENANCE,
    registry: MOCK_REGISTRY,
    exceptions: MOCK_EXCEPTIONS,
  });
}

function renderTable(overrides: Partial<Parameters<typeof SpecTable>[0]> = {}) {
  const callbacks = {
    onSetValue: vi.fn().mockResolvedValue(undefined),
    onTombstone: vi.fn().mockResolvedValue(undefined),
    onRevert: vi.fn().mockResolvedValue(undefined),
    onAddValueToKey: vi.fn().mockResolvedValue(undefined),
    onAddSpecification: vi.fn(),
    ...(overrides.callbacks ?? {}),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={client}>
      <SpecTable rows={rows()} registry={MOCK_REGISTRY} {...overrides} callbacks={callbacks} />
    </QueryClientProvider>,
  );
  return { ...result, callbacks };
}

describe('the table model', () => {
  it('includes a tombstoned key, which lives only in provenance', () => {
    // The row a values-driven table renders as nothing at all.
    const overflow = rows().find((row) => row.specKey === 'has_overflow');
    expect(overflow).toBeDefined();
    expect(overflow!.tombstoned).toBe(true);
    expect(overflow!.value).toBeNull();
  });

  it('marks a stored key the registry no longer defines', () => {
    const gloss = rows().find((row) => row.specKey === 'gloss_level');
    expect(gloss!.unknownKey).toBe(true);
  });

  it('attaches an open conflict to its own row and no other', () => {
    const withConflict = rows().filter((row) => row.conflict);
    expect(withConflict.map((row) => row.specKey)).toEqual(['shape']);
    expect(withConflict[0].conflict!.proposed).toBe('round');
  });

  it('prefers the registry unit over the copy stored on the value', () => {
    const height = rows().find((row) => row.specKey === 'dim_height');
    expect(height!.unit).toBe('mm');
  });

  it('sorts by label rather than by key', () => {
    const labels = rows().map((row) => row.label);
    expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b)));
  });
});

describe('rendering', () => {
  it('renders every state on one product', () => {
    renderTable();
    expect(screen.getByText('Finish or colour')).toBeInTheDocument();
    expect(screen.getByText('Height')).toBeInTheDocument();
    expect(screen.getByText('Intelligent / smart')).toBeInTheDocument();
    expect(screen.getByText('Model note')).toBeInTheDocument();
  });

  it('shows a tombstoned key as a row reading "Not on this product"', () => {
    renderTable();
    expect(screen.getByText('Not on this product')).toBeInTheDocument();
  });

  it('renders a numeric value with its unit as a suffix', () => {
    renderTable();
    expect(screen.getByText('770 mm')).toBeInTheDocument();
  });

  it('renders a boolean as Yes rather than as true', () => {
    renderTable();
    expect(screen.getByText('Yes')).toBeInTheDocument();
  });

  it('says a key the registry no longer defines is not in the registry', () => {
    renderTable();
    expect(screen.getByText('Not in the registry')).toBeInTheDocument();
  });

  it('offers no row actions for a key the registry no longer defines', () => {
    renderTable();
    expect(screen.queryByLabelText('Edit Gloss level')).not.toBeInTheDocument();
  });

  it('marks the row carrying an open conflict, and only that row', () => {
    const { container } = renderTable();
    const marks = container.querySelectorAll('[data-spec-conflict]');
    expect(marks).toHaveLength(1);
    expect(marks[0].getAttribute('data-spec-conflict')).toBe('shape');
  });

  it('offers no resolve action anywhere - the value IS the resolution', () => {
    renderTable();
    expect(screen.queryByText(/resolve/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dismiss/i)).not.toBeInTheDocument();
  });

  it('renders the empty state with its own CTA rather than hiding the section', () => {
    renderTable({ rows: [] });
    expect(screen.getByText('Nothing has been read from this product yet')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /add a specification/i }).length).toBeGreaterThan(0);
  });

  it('hides every edit affordance when the caller says the user may not edit', () => {
    renderTable({ canEdit: false });
    expect(screen.queryByLabelText('Edit Finish or colour')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add a specification/i })).not.toBeInTheDocument();
  });
});

describe('the source badge', () => {
  it('names each source the way a person would', () => {
    renderTable();
    expect(screen.getAllByText('Set by hand').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Flyer').length).toBeGreaterThan(0);
    // Two rows read from the description - `material` and the key the registry has
    // since dropped - so this is deliberately getAllByText.
    expect(screen.getAllByText('Description').length).toBeGreaterThan(0);
    expect(screen.getByText('Category')).toBeInTheDocument();
  });

  it('gives an authored source the affirmative pill and a machine one the muted pill', () => {
    const { container } = renderTable();
    const authored = container.querySelector('[data-spec-source="human"] span');
    const machine = container.querySelector('[data-spec-source="flyer"] span');
    expect(authored).toHaveClass(...statusPillClass('manual').split(' '));
    expect(machine).toHaveClass(...statusPillClass('ai').split(' '));
  });

  it('keeps the evidence behind a tap, not in a column of its own', async () => {
    const { container } = renderTable();
    // Nothing on screen until asked for: a permanent column pushes the value itself
    // off the right of a phone.
    expect(container.querySelector('[data-spec-evidence]')).toBeNull();

    fireEvent.click(container.querySelector('[data-spec-source="flyer"]') as HTMLElement);
    expect(container.querySelector('[data-spec-evidence]')).not.toBeNull();
    expect(screen.getByText(/Washdown With Rimless/)).toBeInTheDocument();
  });

  it('labels an authored strip "Set by" rather than "Read from"', async () => {
    const { container } = renderTable();
    fireEvent.click(container.querySelector('[data-spec-source="human"]') as HTMLElement);
    expect(screen.getByText('Set by:')).toBeInTheDocument();
  });
});

describe('editing in place', () => {
  it('swaps the value cell to an input when the value is clicked', async () => {
    const { container } = renderTable();
    fireEvent.click(container.querySelector('[data-spec-value="model_note"]') as HTMLElement);
    expect(container.querySelector('[data-spec-editor="model_note"]')).not.toBeNull();
  });

  it('opens the editor from the row edit icon too', async () => {
    const { container } = renderTable();
    fireEvent.click(screen.getByLabelText('Edit Model note'));
    expect(container.querySelector('[data-spec-editor="model_note"]')).not.toBeNull();
  });

  it('keeps every other row out of edit - one open editor at a time', async () => {
    const { container } = renderTable();
    fireEvent.click(screen.getByLabelText('Edit Model note'));
    fireEvent.click(screen.getByLabelText('Edit Material'));
    expect(container.querySelector('[data-spec-editor="model_note"]')).toBeNull();
    expect(container.querySelector('[data-spec-editor="material"]')).not.toBeNull();
  });

  it('gives a free-text key a typed input carrying the current value', async () => {
    renderTable();
    fireEvent.click(screen.getByLabelText('Edit Model note'));
    expect(screen.getByLabelText('Model note')).toHaveValue('Second batch, revised trap');
  });

  it('shows the unit as a suffix on a numeric editor, where it cannot be typed', async () => {
    const { container } = renderTable();
    fireEvent.click(screen.getByLabelText('Edit Height'));
    const editor = container.querySelector('[data-spec-editor="dim_height"]') as HTMLElement;
    expect(within(editor).getByText('mm')).toBeInTheDocument();
    expect(within(editor).getByLabelText('Height')).toHaveAttribute('type', 'number');
  });

  it('saves the typed value and closes the editor', async () => {
    const { container, callbacks } = renderTable();
    fireEvent.click(screen.getByLabelText('Edit Model note'));
    clearInput(screen.getByLabelText('Model note'));
    typeInto(screen.getByLabelText('Model note'), 'Third batch');
    fireEvent.click(screen.getByLabelText('Save Model note'));

    expect(callbacks.onSetValue).toHaveBeenCalledWith('model_note', 'Third batch');
    await waitFor(() =>
      expect(container.querySelector('[data-spec-editor="model_note"]')).toBeNull(),
    );
  });

  it('sends a numeric key a number, not the string that was typed', async () => {
    const { callbacks } = renderTable();
    fireEvent.click(screen.getByLabelText('Edit Height'));
    clearInput(screen.getByLabelText('Height'));
    typeInto(screen.getByLabelText('Height'), '820');
    fireEvent.click(screen.getByLabelText('Save Height'));
    expect(callbacks.onSetValue).toHaveBeenCalledWith('dim_height', 820);
  });

  it('cancel leaves the value alone', async () => {
    const { container, callbacks } = renderTable();
    fireEvent.click(screen.getByLabelText('Edit Model note'));
    fireEvent.click(screen.getByLabelText('Cancel editing Model note'));
    expect(callbacks.onSetValue).not.toHaveBeenCalled();
    expect(container.querySelector('[data-spec-editor="model_note"]')).toBeNull();
  });

  it('refuses to save an empty value - a blank is a removal wearing one', async () => {
    renderTable();
    fireEvent.click(screen.getByLabelText('Edit Model note'));
    clearInput(screen.getByLabelText('Model note'));
    expect(screen.getByLabelText('Save Model note')).toBeDisabled();
  });

  it('opens an editor the caller asks for, so the picker lands on the row', async () => {
    const { container } = renderTable({ openEditorFor: 'material' });
    await waitFor(() =>
      expect(container.querySelector('[data-spec-editor="material"]')).not.toBeNull(),
    );
  });

  /**
   * The picker only ever names keys the product does NOT carry, so "open the editor on
   * that row" is a request for a row that does not exist yet. Waiting for one to turn up
   * meant the dialog closed and the table was unchanged - for an existing key and a
   * freshly created one alike, with no request made and nothing to see after a refresh.
   */
  it('makes a row for a key the product does not carry, and opens its editor', async () => {
    // `seat_material` is in MOCK_REGISTRY and in neither MOCK_VALUES nor MOCK_PROVENANCE.
    expect(rows().some((row) => row.specKey === 'seat_material')).toBe(false);

    const { container } = renderTable({ openEditorFor: 'seat_material' });

    await waitFor(() =>
      expect(container.querySelector('[data-spec-editor="seat_material"]')).not.toBeNull(),
    );
    expect(screen.getByText('Seat cover material')).toBeInTheDocument();
  });

  it('saves the value typed on that new row through the same callback', async () => {
    // A key with no vocabulary, so the editor is the typed input rather than a select.
    const registry = [
      ...MOCK_REGISTRY,
      {
        spec_key: 'warranty_months',
        label: 'Warranty',
        data_type: 'numeric',
        unit: 'months',
        allowed_values: [],
      },
    ];
    const { callbacks } = renderTable({ registry, openEditorFor: 'warranty_months' });

    await waitFor(() => expect(screen.getByLabelText('Warranty')).toBeInTheDocument());
    typeInto(screen.getByLabelText('Warranty'), '24');
    fireEvent.click(screen.getByLabelText('Save Warranty'));

    await waitFor(() => expect(callbacks.onSetValue).toHaveBeenCalledWith('warranty_months', 24));
  });

  it('cancelling that new row leaves the table exactly as it was', async () => {
    const { container, callbacks } = renderTable({ openEditorFor: 'seat_material' });

    await waitFor(() =>
      expect(container.querySelector('[data-spec-editor="seat_material"]')).not.toBeNull(),
    );
    fireEvent.click(screen.getByLabelText('Cancel editing Seat cover material'));

    expect(callbacks.onSetValue).not.toHaveBeenCalled();
    expect(screen.queryByText('Seat cover material')).not.toBeInTheDocument();
  });

  it('sorts that new row in by label rather than dropping it at the bottom', async () => {
    const { container } = renderTable({ openEditorFor: 'seat_material' });

    await waitFor(() =>
      expect(container.querySelector('[data-spec-editor="seat_material"]')).not.toBeNull(),
    );
    const labels = Array.from(container.querySelectorAll('tbody tr td:first-child')).map((cell) =>
      (cell.textContent ?? '').trim(),
    );
    expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b)));
  });
});

describe('removing, by name', () => {
  it('offers the two intents by name rather than one "delete"', async () => {
    renderTable();
    openMenu(screen.getByLabelText('More actions for Material'));
    expect(screen.getByText('This product does not have this spec')).toBeInTheDocument();
    expect(screen.getByText('Reset')).toBeInTheDocument();
    expect(screen.queryByText(/^delete$/i)).not.toBeInTheDocument();
  });

  it('tombstones behind a confirmation carrying "cannot be undone"', async () => {
    const { callbacks } = renderTable();
    openMenu(screen.getByLabelText('More actions for Material'));
    fireEvent.click(screen.getByText('This product does not have this spec'));

    expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(callbacks.onTombstone).toHaveBeenCalledWith('material'));
  });

  it('reverts behind its own confirmation', async () => {
    const { callbacks } = renderTable();
    openMenu(screen.getByLabelText('More actions for Material'));
    fireEvent.click(screen.getByText('Reset'));
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(callbacks.onRevert).toHaveBeenCalledWith('material'));
  });

  it('will not tombstone a key that already is one', async () => {
    renderTable();
    openMenu(screen.getByLabelText('More actions for Overflow'));
    expect(
      screen.getByText('This product does not have this spec').closest('[role="menuitem"]'),
    ).toHaveAttribute('aria-disabled', 'true');
  });
});
