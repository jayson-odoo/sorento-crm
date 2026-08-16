/**
 * The add-a-specification picker - AC-A.8, A.9, A.10.
 *
 * The three things worth pinning: applicable keys come first and everything else is one
 * more click away; a user without `spec_registry.add` is told who to ask rather than
 * shown a dead button; and the duplicate check runs BEFORE the create can submit, not
 * after - offering the match afterwards would mean the key already exists by then.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { toast } from 'sonner';

import { AddSpecificationDialog, toSpecKey } from './AddSpecificationDialog';
import type { SpecKeyDefinition } from './types';

const APPLICABLE: SpecKeyDefinition[] = [
  { spec_key: 'flush_type', label: 'Flush type', data_type: 'enum', unit: null, allowed_values: [] },
];
const OTHER: SpecKeyDefinition[] = [
  { spec_key: 'bowl_count', label: 'Number of bowls', data_type: 'numeric', unit: null, allowed_values: [] },
  { spec_key: 'drainer', label: 'Drainer board', data_type: 'boolean', unit: null, allowed_values: [] },
];
const HELD: SpecKeyDefinition[] = [
  { spec_key: 'finish', label: 'Finish', data_type: 'enum', unit: null, allowed_values: [] },
];

function renderDialog(overrides: Partial<Parameters<typeof AddSpecificationDialog>[0]> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    applicableKeys: APPLICABLE,
    otherKeys: OTHER,
    canCreateKey: true,
    onPick: vi.fn(),
    onCreateKey: vi.fn().mockResolvedValue(undefined),
    onCheckSimilar: vi.fn().mockResolvedValue(null),
    ...overrides,
  };
  return { ...render(<AddSpecificationDialog {...props} />), props };
}

/** Open the key search and type a name, the way a person reaches "Create". */
function searchFor(name: string) {
  fireEvent.click(document.querySelector('[data-slot="searchable-select-trigger"]')!);
  fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: name } });
}

/** The last entry of the list: "Create ..." or "... already exists". */
function lastEntry(): HTMLElement | null {
  return document.querySelector('[data-slot="searchable-select-create"]');
}

/** Type a brand-new name and take the list's Create entry - lands on the type step. */
function startCreating(name: string) {
  searchFor(name);
  fireEvent.click(lastEntry()!);
}

describe('choosing a key', () => {
  it('keeps everything else behind one more click', () => {
    renderDialog();
    expect(screen.getByText('Show every specification (2 more)')).toBeInTheDocument();
  });

  it('does not offer the extra click when there is nothing behind it', () => {
    renderDialog({ otherKeys: [] });
    expect(screen.queryByText(/Show every specification/)).not.toBeInTheDocument();
  });

  it('cannot add until a key is picked', () => {
    renderDialog();
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();
  });
});

describe('who may create a key', () => {
  it('offers Create as the last entry of the search list to a user who holds the grant', () => {
    renderDialog();
    searchFor('Seat hinge type');
    expect(lastEntry()).toHaveTextContent('Create “Seat hinge type”');
  });

  it('tells a user without the grant who to ask, and offers no Create entry', () => {
    renderDialog({ canCreateKey: false });
    expect(
      screen.getByText('Ask an administrator for the Add Spec Registry permission.'),
    ).toBeInTheDocument();
    searchFor('Seat hinge type');
    expect(lastEntry()).toBeNull();
  });

  it('points a typed name that already IS a key at that key instead of Create', () => {
    const { props } = renderDialog();
    searchFor('flush type');
    expect(lastEntry()).toHaveTextContent('Flush type already exists');
    fireEvent.click(lastEntry()!);
    // Picked, not created - the Add button now carries it through.
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(props.onPick).toHaveBeenCalledWith('flush_type');
    expect(props.onCreateKey).not.toHaveBeenCalled();
  });

  it('reveals a key hidden behind "show everything" when its name is typed', () => {
    const { props } = renderDialog();
    searchFor('Number of bowls');
    fireEvent.click(lastEntry()!);
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(props.onPick).toHaveBeenCalledWith('bowl_count');
  });

  it('says a name the product already carries is on it, and offers no Create', () => {
    // Neither offerable list holds it - both are built from `!held` - so without the
    // held keys the search read "no such key" and offered to create a second one.
    const { props } = renderDialog({ heldKeys: HELD });
    searchFor('Finish');

    expect(lastEntry()).toHaveTextContent('Finish is already on this product');
    expect(lastEntry()).not.toHaveTextContent('Create');

    fireEvent.click(lastEntry()!);
    expect(props.onCreateKey).not.toHaveBeenCalled();
    expect(props.onPick).not.toHaveBeenCalled();
    // Still on the search step, not the type question.
    expect(screen.queryByLabelText('What kind of answer it has')).not.toBeInTheDocument();
  });
});

describe('creating a key', () => {
  it('asks what kind of answer it has, with the typed name carried over', () => {
    renderDialog();
    startCreating('Seat hinge type');
    expect(screen.getByText('What kind of answer it has')).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toHaveValue('Seat hinge type');
  });

  it('checks for a duplicate BEFORE creating, and creates when there is none', async () => {
    const { props } = renderDialog();
    startCreating('Seat hinge type');
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(props.onCheckSimilar).toHaveBeenCalledWith('Seat hinge type'));
    await waitFor(() =>
      expect(props.onCreateKey).toHaveBeenCalledWith({
        spec_key: 'seat_hinge_type',
        label: 'Seat hinge type',
        data_type: 'enum',
      }),
    );
    // And hands the fresh key to the table, exactly as picking an existing one does -
    // a key created and not set on this product was the dead end the person was in.
    await waitFor(() => expect(props.onPick).toHaveBeenCalledWith('seat_hinge_type'));
  });

  it('offers the existing key instead, and creates nothing', async () => {
    const { props } = renderDialog({
      onCheckSimilar: vi.fn().mockResolvedValue({
        spec_key: 'finish',
        label: 'Finish or colour',
        matched_on: 'label',
        matched_text: 'Finish or colour',
      }),
    });
    startCreating('Finish Or Colour');
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(screen.getByText('Finish or colour already exists.')).toBeInTheDocument());
    expect(props.onCreateKey).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Use Finish or colour instead' }));
    expect(props.onPick).toHaveBeenCalledWith('finish');
  });

  it('says which WORD collided when the match is on a synonym', async () => {
    renderDialog({
      onCheckSimilar: vi.fn().mockResolvedValue({
        spec_key: 'finish',
        label: 'Finish or colour',
        matched_on: 'synonym',
        matched_text: 'surface colour',
      }),
    });
    startCreating('Surface colour');
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(
        screen.getByText('"surface colour" is already a word for Finish or colour.'),
      ).toBeInTheDocument(),
    );
  });

  it('cannot submit an empty name', () => {
    renderDialog();
    startCreating('Seat hinge type');
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
  });

  it('toasts when the duplicate check itself fails, rather than resetting silently', async () => {
    const { props } = renderDialog({
      onCheckSimilar: vi.fn().mockRejectedValue(new Error('Network down')),
    });
    startCreating('Seat hinge type');
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Network down', { duration: 10_000 }),
    );
    expect(props.onCreateKey).not.toHaveBeenCalled();
  });
});

describe('toSpecKey', () => {
  it.each([
    ['Tap hole count', 'tap_hole_count'],
    ['  Finish / colour  ', 'finish_colour'],
    ['Seat-cover material', 'seat_cover_material'],
  ])('turns %s into %s', (label, expected) => {
    expect(toSpecKey(label)).toBe(expected);
  });
});
