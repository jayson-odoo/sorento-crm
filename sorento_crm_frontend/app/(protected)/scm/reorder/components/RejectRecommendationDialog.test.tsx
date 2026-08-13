/**
 * SCM M4 Slice B - RejectRecommendationDialog (AC-M4.8).
 * Destructive AlertDialog confirm with a REQUIRED reason: submit is blocked +
 * an inline error shows when the reason is empty; a filled reason emits the
 * payload; the destructive button carries the destructive styling.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

import { RejectRecommendationDialog } from './RejectRecommendationDialog';
import type { ReorderRecommendation } from '../types/reorder.types';

const rec = { id: 'rec-1', sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm' } as ReorderRecommendation;

function renderDialog(over: Partial<React.ComponentProps<typeof RejectRecommendationDialog>> = {}) {
  const onSubmit = vi.fn();
  render(
    <RejectRecommendationDialog
      rec={rec}
      open
      onOpenChange={vi.fn()}
      onSubmit={onSubmit}
      isSubmitting={false}
      {...over}
    />,
  );
  return { onSubmit };
}

beforeEach(() => vi.clearAllMocks());

describe('RejectRecommendationDialog (AC-M4.8)', () => {
  it('renders the destructive confirm naming the rec', () => {
    renderDialog();
    expect(screen.getByText('Reject this recommendation?')).toBeInTheDocument();
    expect(screen.getByText(/CW-BASIN-450/)).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: /Reject recommendation/i });
    expect(submit.className).toContain('bg-destructive');
  });

  it('blocks submit and shows the required-reason error when empty', () => {
    const { onSubmit } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: /Reject recommendation/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/A reason is required to reject/i)).toBeInTheDocument();
  });

  it('emits the reason payload once a reason is entered', () => {
    const { onSubmit } = renderDialog();
    fireEvent.change(screen.getByPlaceholderText(/Why reject/i), { target: { value: 'discontinued' } });
    fireEvent.click(screen.getByRole('button', { name: /Reject recommendation/i }));
    expect(onSubmit).toHaveBeenCalledWith({ reason_text: 'discontinued' });
  });
});
