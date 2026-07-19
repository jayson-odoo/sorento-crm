import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { VoidDialog } from './VoidDialog';

// jsdom doesn't implement these; radix touches them on open.
beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

function renderDialog(props: Partial<React.ComponentProps<typeof VoidDialog>> = {}) {
  const onConfirm = props.onConfirm ?? vi.fn().mockResolvedValue(undefined);
  const onOpenChange = props.onOpenChange ?? vi.fn();
  render(
    <VoidDialog open onOpenChange={onOpenChange} onConfirm={onConfirm} {...props} />,
  );
  return { onConfirm, onOpenChange };
}

describe('VoidDialog', () => {
  it('renders the destructive confirm with a required reason field', () => {
    renderDialog();
    expect(screen.getByText('Void this form?')).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Reason/)).toBeInTheDocument();
    // Action button is disabled until a valid reason is entered.
    expect(screen.getByRole('button', { name: /void form/i })).toBeDisabled();
  });

  it('shows an inline error and does not confirm when the reason is too short', async () => {
    const { onConfirm } = renderDialog();
    const textarea = screen.getByLabelText(/Reason/);
    fireEvent.change(textarea, { target: { value: 'ab' } });
    fireEvent.blur(textarea);
    expect(
      await screen.findByText(/at least 3 characters is required/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /void form/i })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('confirms with the trimmed reason and closes on success', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const onOpenChange = vi.fn();
    renderDialog({ onConfirm, onOpenChange });

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: '  Duplicate submission  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /void form/i }));

    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith('Duplicate submission'),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('stays open when the confirm mutation rejects', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('boom'));
    const onOpenChange = vi.fn();
    renderDialog({ onConfirm, onOpenChange });

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'valid reason' },
    });
    fireEvent.click(screen.getByRole('button', { name: /void form/i }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
