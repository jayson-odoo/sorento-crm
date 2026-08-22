/**
 * The buyer's own MoQ (20 Aug live test, commit cefa08670): "MoQ is varying from time to
 * time so they don't maintain it ... let them input it, and when they change it, our
 * calculation should recalculate."
 *
 * The one rule mirrored from `PlanLevelCell`: the cell must never hide what master data
 * actually says. Overridden shows the buyer's own number AND a muted "master N" subline;
 * withdrawing (clearing, or typing the master figure back) reads as a withdrawal, not a
 * fresh override.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { PlanMoqCell } from './PlanMoqCell';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

describe('PlanMoqCell - read-only (no onChange, or disabled)', () => {
  it('shows the effective MoQ plainly, with no input', () => {
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} />);

    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  });

  it('renders an em dash, never a zero, when no MoQ is on file', () => {
    render(<PlanMoqCell moq={null} masterMoq={null} isOverride={false} />);

    const dash = screen.getByTitle('No MOQ on file for this supplier');
    expect(dash).toHaveTextContent('-');
  });

  it('is read-only when disabled, even with an onChange handler supplied', () => {
    const onChange = vi.fn();
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} onChange={onChange} disabled />);

    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('shows the sell-through note beneath the figure when one is supplied', () => {
    render(
      <PlanMoqCell
        moq={100}
        masterMoq={100}
        isOverride={false}
        note={{ text: '+40 over need', warn: true, title: 'MOQ pumps the buy above need' }}
      />,
    );

    expect(screen.getByText('+40 over need')).toBeInTheDocument();
  });
});

describe('PlanMoqCell - editable, not overridden', () => {
  it('defaults the input to the master figure, with no "master N" subline', () => {
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} onChange={vi.fn()} />);

    const input = screen.getByLabelText('MOQ') as HTMLInputElement;
    expect(input.value).toBe('100');
    expect(screen.queryByText(/master \d/)).not.toBeInTheDocument();
    expect(screen.queryByText('edited')).not.toBeInTheDocument();
  });

  it('typing a new number and blurring records the override', async () => {
    const onChange = vi.fn();
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} onChange={onChange} />);

    const input = screen.getByLabelText('MOQ');
    fireEvent.change(input, { target: { value: '15' } });
    fireEvent.blur(input);

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(15));
  });

  it('pressing Enter commits the same way blur does', async () => {
    const onChange = vi.fn();
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} onChange={onChange} />);

    const input = screen.getByLabelText('MOQ');
    input.focus();
    fireEvent.change(input, { target: { value: '15' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(15));
  });

  it('leaving the field untouched never calls onChange', () => {
    const onChange = vi.fn();
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} onChange={onChange} />);

    fireEvent.blur(screen.getByLabelText('MOQ'));

    expect(onChange).not.toHaveBeenCalled();
  });

  it('a negative or non-numeric entry is rejected, never sent as an override, and says so', () => {
    // S8 (code review, 20 Aug 2026): dropping an invalid edit used to give the buyer no
    // feedback at all - it just silently did not save.
    const onChange = vi.fn();
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} onChange={onChange} />);

    const input = screen.getByLabelText('MOQ') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '-5' } });
    fireEvent.blur(input);

    expect(onChange).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('MOQ must be a whole number of 0 or more.');
    // Left on screen to fix, not silently reverted.
    expect(input.value).toBe('-5');
  });

  it('a failed save is reported with a toast, not left as an unhandled rejection', async () => {
    // S8: `void commit()` on blur means a rejected onChange used to vanish with nothing
    // shown to the buyer.
    const onChange = vi.fn().mockRejectedValue(new Error('Failed to save the MOQ.'));
    render(<PlanMoqCell moq={100} masterMoq={100} isOverride={false} onChange={onChange} />);

    const input = screen.getByLabelText('MOQ');
    fireEvent.change(input, { target: { value: '15' } });
    fireEvent.blur(input);

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(15));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to save the MOQ.'));
  });

  it('a rejected withdrawal (clearing to empty) is also reported', async () => {
    const onChange = vi.fn().mockRejectedValue(new Error('Failed to save the MOQ.'));
    render(<PlanMoqCell moq={15} masterMoq={100} isOverride onChange={onChange} />);

    const input = screen.getByLabelText('MOQ');
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(null));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to save the MOQ.'));
  });
});

describe('PlanMoqCell - overridden', () => {
  it('shows the buyer’s figure with the muted master figure beneath it', () => {
    render(<PlanMoqCell moq={15} masterMoq={100} isOverride onChange={vi.fn()} />);

    const input = screen.getByLabelText('MOQ') as HTMLInputElement;
    expect(input.value).toBe('15');
    expect(screen.getByText('master 100')).toBeInTheDocument();
    // the note is suppressed while overridden - the master subline takes its place
    expect(screen.queryByText(/over need/)).not.toBeInTheDocument();
  });

  it('reads "edited" when there is no master figure to show beneath it', () => {
    render(<PlanMoqCell moq={15} masterMoq={null} isOverride onChange={vi.fn()} />);

    expect(screen.getByText('edited')).toBeInTheDocument();
  });

  it('clearing the field back to empty withdraws the override', async () => {
    const onChange = vi.fn();
    render(<PlanMoqCell moq={15} masterMoq={100} isOverride onChange={onChange} />);

    const input = screen.getByLabelText('MOQ');
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(null));
  });

  it('typing the master figure back is a withdrawal, not a fresh override', async () => {
    const onChange = vi.fn();
    render(<PlanMoqCell moq={15} masterMoq={100} isOverride onChange={onChange} />);

    const input = screen.getByLabelText('MOQ');
    fireEvent.change(input, { target: { value: '100' } });
    fireEvent.blur(input);

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(null));
  });
});
