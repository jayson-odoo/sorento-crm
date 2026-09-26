/**
 * S3-4: the dismiss dialog requires a reason of at least 3 characters and names the count.
 * S3-2: the only verb anywhere in this dialog is "Dismiss with a reason" / "Dismiss N" - no
 * "Override with a reason", "Clear with a reason" or a second confirmation step (R3, R20).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DismissReasonDialog } from './DismissReasonDialog';

describe('DismissReasonDialog', () => {
  it('titles itself "Dismiss with a reason" for every severity', () => {
    render(
      <DismissReasonDialog
        severity="hard"
        detail="The schedule only places 0."
        ids={['f1']}
        onDone={vi.fn()}
        onDismiss={vi.fn()}
        submitting={false}
      />,
    );
    expect(screen.getByText('Dismiss with a reason')).toBeInTheDocument();
    expect(screen.queryByText(/Override with a reason/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Clear with a reason/)).not.toBeInTheDocument();
  });

  it('shows the severity pill matching the finding', () => {
    render(
      <DismissReasonDialog
        severity="warn"
        detail="Ordered in SET, no item package."
        ids={['f1']}
        onDone={vi.fn()}
        onDismiss={vi.fn()}
        submitting={false}
      />,
    );
    expect(screen.getByText('Needs acknowledgement')).toBeInTheDocument();
  });

  it('names the count on the confirm button, and disables it under 3 characters', () => {
    render(
      <DismissReasonDialog
        severity="hard"
        detail="Duplicated across 8 lines."
        ids={['f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8']}
        onDone={vi.fn()}
        onDismiss={vi.fn()}
        submitting={false}
      />,
    );
    const confirm = screen.getByRole('button', { name: 'Dismiss 8' });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: 'ok' } });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: 'Confirmed by email.' } });
    expect(confirm).not.toBeDisabled();
  });

  it('refuses a whitespace-only reason', () => {
    render(
      <DismissReasonDialog
        severity="info"
        detail="For information."
        ids={['f1']}
        onDone={vi.fn()}
        onDismiss={vi.fn()}
        submitting={false}
      />,
    );
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Dismiss 1' })).toBeDisabled();
  });

  it('calls onDismiss once with every underlying id and the one typed reason, then closes', async () => {
    const onDismiss = vi.fn().mockResolvedValue(undefined);
    const onDone = vi.fn();
    render(
      <DismissReasonDialog
        severity="hard"
        detail="Not identified."
        ids={['f1', 'f2']}
        onDone={onDone}
        onDismiss={onDismiss}
        submitting={false}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Confirmed against the printed total.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss 2' }));

    await waitFor(() =>
      expect(onDismiss).toHaveBeenCalledWith(['f1', 'f2'], 'Confirmed against the printed total.'),
    );
    expect(onDismiss).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('cancels without calling onDismiss', () => {
    const onDismiss = vi.fn();
    const onDone = vi.fn();
    render(
      <DismissReasonDialog
        severity="hard"
        detail="Not identified."
        ids={['f1']}
        onDone={onDone}
        onDismiss={onDismiss}
        submitting={false}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onDismiss).not.toHaveBeenCalled();
    expect(onDone).toHaveBeenCalled();
  });
});
