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
  it('offers the create route to a user who holds the grant', () => {
    renderDialog();
    expect(screen.getByText('None of these — create a new specification')).toBeInTheDocument();
  });

  it('tells a user without the grant who to ask, rather than showing a dead button', () => {
    renderDialog({ canCreateKey: false });
    expect(screen.queryByText('None of these — create a new specification')).not.toBeInTheDocument();
    expect(
      screen.getByText('Ask an administrator for the Add Spec Registry permission.'),
    ).toBeInTheDocument();
  });
});

describe('creating a key', () => {
  it('asks what kind of answer it has, because the API refuses free text', () => {
    renderDialog();
    fireEvent.click(screen.getByText('None of these — create a new specification'));
    expect(screen.getByText('What kind of answer it has')).toBeInTheDocument();
  });

  it('checks for a duplicate BEFORE creating, and creates when there is none', async () => {
    const { props } = renderDialog();
    fireEvent.click(screen.getByText('None of these — create a new specification'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Seat hinge type' } });
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
    fireEvent.click(screen.getByText('None of these — create a new specification'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Finish Or Colour' } });
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
    fireEvent.click(screen.getByText('None of these — create a new specification'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Surface colour' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(
        screen.getByText('"surface colour" is already a word for Finish or colour.'),
      ).toBeInTheDocument(),
    );
  });

  it('cannot submit an empty name', () => {
    renderDialog();
    fireEvent.click(screen.getByText('None of these — create a new specification'));
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
  });

  it('toasts when the duplicate check itself fails, rather than resetting silently', async () => {
    const { props } = renderDialog({
      onCheckSimilar: vi.fn().mockRejectedValue(new Error('Network down')),
    });
    fireEvent.click(screen.getByText('None of these — create a new specification'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Seat hinge type' } });
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
