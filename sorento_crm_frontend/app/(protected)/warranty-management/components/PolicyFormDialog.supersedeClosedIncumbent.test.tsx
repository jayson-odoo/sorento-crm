/**
 * `PolicyFormDialog` (supersede mode) — S7b Phase 2c follow-up gate, item 3.
 *
 * AC-P26 says the dialog states the resulting window for BOTH policies. The
 * existing gate (`PolicyFormDialog.test.tsx`) only pins the OPEN-ENDED
 * incumbent branch (computes the close date as the day before the successor
 * starts). This file pins the OTHER branch: an incumbent that already has an
 * `effective_to` is not touched by Supersede — the server refuses to
 * supersede an already-closed policy — so the dialog must say it "already
 * ends" its EXISTING end date, and must NOT assert a computed close date the
 * server would reject.
 *
 * Both branches are asserted here (not just the closed one) so the two
 * cannot silently converge on the same wrong text and still look "done".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PolicyFormDialog } from './PolicyFormDialog';
import type { WarrantyPolicyRow } from '../types/warranty-config.types';

function policy(over: Partial<WarrantyPolicyRow>): WarrantyPolicyRow {
  return {
    id: 'pol-15',
    version: 'v15',
    effective_from: '2000-01-01',
    effective_to: null,
    policy_text: null,
    source_attachment_name: null,
    term_count: 41,
    created_at: '2000-01-01T00:00:00',
    updated_at: null,
    ...over,
  };
}

describe('PolicyFormDialog (supersede mode) — AC-P26, already-closed incumbent branch', () => {
  it('an OPEN-ENDED incumbent: states the COMPUTED close date (day before the successor starts)', () => {
    render(
      <PolicyFormDialog
        open
        onOpenChange={vi.fn()}
        mode="supersede"
        incumbent={policy({ version: 'v15', effective_to: null })}
        onSubmit={vi.fn()}
        isSubmitting={false}
        error={null}
      />,
    );

    fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-09-01' } });

    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent ?? '').toMatch(/closes/i);
    expect(dialog.textContent ?? '').toMatch(/2026-08-31/);
    expect(dialog.textContent ?? '').not.toMatch(/already ends/i);
  });

  it('an ALREADY-CLOSED incumbent: states its EXISTING end date as "already ends", not a computed close date', () => {
    render(
      <PolicyFormDialog
        open
        onOpenChange={vi.fn()}
        mode="supersede"
        incumbent={policy({ version: 'v15', effective_to: '2026-06-30' })}
        onSubmit={vi.fn()}
        isSubmitting={false}
        error={null}
      />,
    );

    fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-09-01' } });

    const dialog = screen.getByRole('dialog');
    // States the incumbent's REAL end date...
    expect(dialog.textContent ?? '').toMatch(/already ends/i);
    expect(dialog.textContent ?? '').toMatch(/2026-06-30/);
    // ...and does NOT claim the server would move it to the day before the
    // successor starts (2026-08-31) — that close date would be refused.
    expect(dialog.textContent ?? '').not.toMatch(/2026-08-31/);
    expect(dialog.textContent ?? '').not.toMatch(/\bcloses\b/i);
  });
});
