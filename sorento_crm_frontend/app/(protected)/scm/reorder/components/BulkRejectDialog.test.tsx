/**
 * SCM M4 Slice B - BulkRejectDialog (AC-M4.8/M4.9).
 * Count-bearing destructive AlertDialog with ONE shared required reason:
 * pluralised title/button, submit blocked until a reason is entered, one reason
 * applied to all selected rows.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

import { BulkRejectDialog } from './BulkRejectDialog';

function renderDialog(over: Partial<React.ComponentProps<typeof BulkRejectDialog>> = {}) {
  const onSubmit = vi.fn();
  render(
    <BulkRejectDialog count={3} open onOpenChange={vi.fn()} onSubmit={onSubmit} isSubmitting={false} {...over} />,
  );
  return { onSubmit };
}

beforeEach(() => vi.clearAllMocks());

describe('BulkRejectDialog (AC-M4.8/M4.9)', () => {
  it('renders a count-bearing pluralised title + destructive button', () => {
    renderDialog({ count: 3 });
    expect(screen.getByText('Reject 3 recommendations?')).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: /Reject 3 recommendations/i });
    expect(submit.className).toContain('bg-destructive');
  });

  it('renders singular copy for a single selection', () => {
    renderDialog({ count: 1 });
    expect(screen.getByText('Reject 1 recommendation?')).toBeInTheDocument();
  });

  it('blocks submit and shows the required-reason error when empty', () => {
    const { onSubmit } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: /Reject 3 recommendations/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/A reason is required to reject/i)).toBeInTheDocument();
  });

  it('emits the one shared reason on submit', () => {
    const { onSubmit } = renderDialog();
    fireEvent.change(screen.getByPlaceholderText(/Why reject these/i), { target: { value: 'overstocked' } });
    fireEvent.click(screen.getByRole('button', { name: /Reject 3 recommendations/i }));
    expect(onSubmit).toHaveBeenCalledWith('overstocked');
  });
});
