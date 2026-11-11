/**
 * NON-CANCELLABLE-ITEMS: an overridable 409 opens the dialog listing the refused lines; Override
 * retries the same call with the typed reason. Values invented.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NonCancellableRefusalError } from '../lib/nonCancellable';
import { useNonCancellableOverride } from './useNonCancellableOverride';

const refusal = new NonCancellableRefusalError('Non-cancellable: Bathtub X', {
  can_override: true,
  lines: [{ label: 'Bathtub X', from_qty: 5, to_qty: 3 }],
});

function Harness({ run }: { run: (vars: string, reason?: string) => Promise<unknown> }) {
  const { attempt, dialog } = useNonCancellableOverride<string>(run);
  return (
    <>
      <button type="button" onClick={() => void attempt('amendment-1')}>
        Publish
      </button>
      {dialog}
    </>
  );
}

describe('useNonCancellableOverride', () => {
  it('asks for a reason on an overridable refusal and retries with it', async () => {
    const run = vi
      .fn<(vars: string, reason?: string) => Promise<unknown>>()
      .mockRejectedValueOnce(refusal)
      .mockResolvedValueOnce({});
    render(<Harness run={run} />);

    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));
    expect(await screen.findByText('Bathtub X')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Override' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: 'Customer agreed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Override' }));

    await waitFor(() => expect(run).toHaveBeenCalledTimes(2));
    expect(run).toHaveBeenLastCalledWith('amendment-1', 'Customer agreed');
    await waitFor(() => expect(screen.queryByText('Bathtub X')).toBeNull());
  });

  it('opens no dialog when the refusal cannot be overridden', async () => {
    const run = vi.fn().mockRejectedValue(
      new NonCancellableRefusalError('A manager can override', { can_override: false, lines: [] }),
    );
    render(<Harness run={run} />);
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('button', { name: 'Override' })).toBeNull();
  });
});
