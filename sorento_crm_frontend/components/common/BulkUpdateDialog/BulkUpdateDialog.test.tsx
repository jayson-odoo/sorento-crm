import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BulkUpdateDialog } from './BulkUpdateDialog';
import type { BulkEditableField } from './types';

const FIELDS: BulkEditableField[] = [
  {
    key: 'status',
    label: 'Status',
    type: 'select',
    options: [
      { value: 'open', label: 'Open' },
      { value: 'resolved', label: 'Resolved' },
    ],
  },
];

function renderDialog(props: Partial<React.ComponentProps<typeof BulkUpdateDialog>> = {}) {
  const onApply = props.onApply ?? vi.fn().mockResolvedValue({ updated: 2, skipped: [] });
  render(
    <BulkUpdateDialog
      open
      onOpenChange={vi.fn()}
      selectedCount={2}
      fields={FIELDS}
      onApply={onApply}
      {...props}
    />,
  );
  return { onApply };
}

// Radix Select calls these on open; jsdom does not implement them.
beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

async function compose() {
  fireEvent.click(screen.getByText('Choose a field…'));
  fireEvent.click(await screen.findByText('Status'));
  fireEvent.click(await screen.findByText('Select a value…'));
  fireEvent.click(await screen.findByText('Open'));
}

describe('BulkUpdateDialog', () => {
  it('renders an empty state when no fields are whitelisted', () => {
    renderDialog({ fields: [] });
    expect(
      screen.getByText('No fields are enabled for bulk update on this list.'),
    ).toBeInTheDocument();
  });

  it('composes -> confirms -> applies and shows the success result', async () => {
    const onApply = vi.fn().mockResolvedValue({ updated: 2, skipped: [] });
    renderDialog({ onApply });

    await compose();
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    // AlertDialog confirmation summarises field = value.
    expect(await screen.findByText('Apply bulk update?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /apply update/i }));

    await waitFor(() => expect(onApply).toHaveBeenCalledWith('status', 'open'));
    // Result stage: its footer shows a single "Done" button.
    expect(await screen.findByRole('button', { name: /^done$/i })).toBeInTheDocument();
    expect(
      screen.getByText('All selected records were updated successfully.'),
    ).toBeInTheDocument();
  });

  it('renders skipped rows with label + reason on a partial result', async () => {
    const onApply = vi.fn().mockResolvedValue({
      updated: 1,
      skipped: [{ id: 's2', label: 'Beta Supplies', reason: 'Record not found.' }],
    });
    renderDialog({ onApply });

    await compose();
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    fireEvent.click(await screen.findByRole('button', { name: /apply update/i }));

    expect(await screen.findByText('Skipped rows')).toBeInTheDocument();
    expect(screen.getByText('Beta Supplies')).toBeInTheDocument();
    expect(screen.getByText('Record not found.')).toBeInTheDocument();
  });

  it('surfaces the error message when onApply rejects', async () => {
    const onApply = vi.fn().mockRejectedValue(new Error('Bulk update exploded'));
    renderDialog({ onApply });

    await compose();
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    fireEvent.click(await screen.findByRole('button', { name: /apply update/i }));

    expect(await screen.findByText('Bulk update exploded')).toBeInTheDocument();
    // Stayed on compose (no result summary rendered).
    expect(screen.queryByText(/records were updated successfully/i)).not.toBeInTheDocument();
  });
});
