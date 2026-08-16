/**
 * `PolicyFormDialog` - S7b Phase 2c gate, Group 2 item 10 (AC-P26 prevention clause).
 *
 * AC-P26: "The Supersede dialog states the resulting window for BOTH policies
 * before it is confirmed (the AC's own example: 'Version 15 closes
 * 2026-08-31; Version 16 runs from 2026-09-01')." Supersede has no undo, so
 * that statement IS the safety mechanism. Once an `effective_from` is entered,
 * the dialog names the incumbent's computed closing date AND the successor's
 * start, and it recomputes when the date is edited rather than showing a stale
 * window.
 *
 * The incumbent is always open ended: both entry points hide Supersede once a
 * policy has an `effective_to`, so there is no closed-incumbent case to pin.
 * The earliest selectable date is pinned in
 * `PolicyFormDialog.supersedeMinDate.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PolicyFormDialog } from './PolicyFormDialog';
import type { WarrantyPolicyRow } from '../types/warranty-config.types';

const INCUMBENT: WarrantyPolicyRow = {
  id: 'pol-15',
  version: 'v15',
  effective_from: '2000-01-01',
  effective_to: null,
  policy_text: null,
  source_attachment_name: null,
  term_count: 41,
  created_at: '2000-01-01T00:00:00',
  updated_at: null,
};

describe('PolicyFormDialog (supersede mode) - AC-P26: states the resulting window for BOTH policies before confirm', () => {
  it('once a new effective_from is entered, the dialog names the incumbent\'s closing date AND the successor\'s start date, before Publish is clicked', () => {
    render(
      <PolicyFormDialog
        open
        onOpenChange={vi.fn()}
        mode="supersede"
        incumbent={INCUMBENT}
        onSubmit={vi.fn()}
        isSubmitting={false}
        error={null}
      />,
    );

    fireEvent.change(screen.getByLabelText('Version'), { target: { value: 'v16' } });
    fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-09-01' } });

    const dialog = screen.getByRole('dialog');
    // The AC's own worked example: the incumbent closes the day BEFORE the
    // successor's start (2026-09-01 -> 2026-08-31), stated in the dialog
    // BEFORE the admin confirms, not discovered afterwards from a toast.
    expect(dialog.textContent ?? '').toMatch(/closes/i);
    expect(dialog.textContent ?? '').toMatch(/2026-08-31/);
    expect(dialog.textContent ?? '').toMatch(/2026-09-01/);
    expect(dialog.textContent ?? '').toMatch(/v15/);
    expect(dialog.textContent ?? '').toMatch(/v16/);

    // This must be true BEFORE Publish is clicked: the dialog is still open
    // and no submit has happened.
    expect(screen.getByRole('button', { name: /^Publish$/i })).toBeInTheDocument();
  });
});
