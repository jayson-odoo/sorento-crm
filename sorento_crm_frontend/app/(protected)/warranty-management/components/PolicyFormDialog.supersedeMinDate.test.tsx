/**
 * `PolicyFormDialog` (supersede mode) - Phase 3 review, AC-P26 finding 1.
 *
 * AC-P21 [BE] refuses a new `effective_from` that is on or before the
 * incumbent's own `effective_from` - the server requires strictly AFTER, not
 * on-or-after. The date input's `min` was set to `incumbent.effective_from`
 * itself, which permits equality. `min` on an `<input type="date">` is
 * inclusive, so an admin could select the incumbent's own start date, get a
 * preview that computes the incumbent closing the day BEFORE it even opened,
 * and only find out the write is impossible when Publish 422s.
 *
 * Two things are gated, matching the ruling:
 *   (a) the `min` attribute is the civil day AFTER `incumbent.effective_from`,
 *       including across a month boundary.
 *   (b) the preview never states a close date earlier than the incumbent's
 *       own start, even when the current `effective_from` value would compute
 *       one (a same-day or before-day selection, which jsdom's date input does
 *       not itself block).
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

function renderSupersede(incumbent: WarrantyPolicyRow) {
  render(
    <PolicyFormDialog
      open
      onOpenChange={vi.fn()}
      mode="supersede"
      incumbent={incumbent}
      onSubmit={vi.fn()}
      isSubmitting={false}
      error={null}
    />,
  );
}

describe('PolicyFormDialog (supersede mode) - AC-P21/AC-P26 finding 1: the min date must match the strictly-after rule', () => {
  it('an incumbent starting 2026-01-01: the "Effective from" input min is 2026-01-02, not the incumbent start itself', () => {
    renderSupersede(policy({ version: 'v15', effective_from: '2026-01-01', effective_to: null }));

    const input = screen.getByLabelText('Effective from') as HTMLInputElement;
    expect(input.min).toBe('2026-01-02');
  });

  it('an incumbent starting 2026-01-31 (month boundary): the min rolls to 2026-02-01, not 2026-02-00 or the incumbent start', () => {
    renderSupersede(policy({ version: 'v15', effective_from: '2026-01-31', effective_to: null }));

    const input = screen.getByLabelText('Effective from') as HTMLInputElement;
    expect(input.min).toBe('2026-02-01');
  });
});

describe('PolicyFormDialog (supersede mode) - AC-P21/AC-P26 finding 1: the preview never states an impossible close date', () => {
  it('effective_from equal to the incumbent start: the preview does not render the naive close date (the day before the incumbent itself began)', () => {
    renderSupersede(policy({ version: 'v15', effective_from: '2026-01-01', effective_to: null }));

    // jsdom does not enforce the `min` attribute, so this reproduces exactly
    // what an admin who typed the date manually, or dragged a picker before
    // the fix, would be shown.
    fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-01-01' } });

    const dialog = screen.getByRole('dialog');
    // A naive `previousCivilDay(effectiveFrom)` computation renders this date
    // - one day before the incumbent's own start - which the server can never
    // accept as v15's close date. That string must never appear.
    expect(dialog.textContent ?? '').not.toMatch(/2025-12-31/);
  });

  it('effective_from BEFORE the incumbent start: the preview still does not render a close date earlier than the incumbent itself began', () => {
    renderSupersede(policy({ version: 'v15', effective_from: '2026-01-01', effective_to: null }));

    fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2025-06-15' } });

    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent ?? '').not.toMatch(/2025-06-14/);
  });
});
