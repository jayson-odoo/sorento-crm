/**
 * `KindRuleFormDialog` - S7b Phase 2c follow-up gate, item 4.
 *
 * AC-P24 is "strict at write, tolerant at READ". Reads are tolerant
 * (`formatMatchTypeLabel` falls back to the raw value, see
 * `warrantyLabels.matchTypeLabel.test.ts`, and the grid half is pinned in
 * `RulesTab.test.tsx`). But this dialog's `match_type` picker is built from
 * the four KNOWN values only (`KIND_RULE_MATCH_TYPES`), so a rule whose
 * STORED value falls outside that set is a real data-integrity hole:
 *
 *   (a) Opening such a rule must SHOW its stored match_type (the raw value),
 *       not an empty/placeholder picker: an admin must see what is actually
 *       in the row before deciding whether to touch it.
 *   (b) Saving WITHOUT touching that field must NOT send `match_type` at
 *       all. These are PATCH endpoints with partial semantics (see the
 *       contract doc atop `services/warrantyConfigService.ts`): an
 *       untouched field must stay untouched server-side, so a legacy row
 *       can have its OTHER fields edited without the write being rejected
 *       (or worse, silently rewriting a value the user never chose).
 *   (c) Changing the field to one of the four valid values must send
 *       EXACTLY that new value.
 *
 * This is a data-integrity path, not a cosmetic one: today it is reachable
 * only via a hand-written row (the database currently holds only
 * `model_list` / `series`), but the backend's own AC-P24 contract commits to
 * tolerating exactly this shape of row.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { KindRuleFormDialog } from './KindRuleFormDialog';
import type { WarrantyKindRef, WarrantyKindRuleRow } from '../types/warranty-config.types';

const KINDS: WarrantyKindRef[] = [
  { id: 'kind-mirror', code: 'mirror_cabinet', name: 'Mirror Cabinet' },
  { id: 'kind-wc', code: 'water_closet', name: 'Water Closet' },
];

const LEGACY_ROW: WarrantyKindRuleRow = {
  id: 'rule-legacy',
  kind_id: 'kind-mirror',
  kind_code: 'mirror_cabinet',
  kind_name: 'Mirror Cabinet',
  // @ts-expect-error - deliberately a match_type the FE's known set does not include.
  match_type: 'something_new',
  match_value: 'ABC',
  priority: 5,
};

describe('KindRuleFormDialog - a legacy row with an unknown match_type (AC-P24 write-side hole)', () => {
  it('(a) shows the STORED raw match_type on open, not an empty/placeholder picker', () => {
    render(
      <KindRuleFormDialog
        open
        onOpenChange={vi.fn()}
        initial={LEGACY_ROW}
        kinds={KINDS}
        defaultKindId=""
        onSubmit={vi.fn()}
        isSubmitting={false}
        error={null}
      />,
    );

    const trigger = screen.getByLabelText('Match type');
    expect(trigger.textContent ?? '').toContain('something_new');
  });

  it('(b) saving WITHOUT touching match_type does not send that key at all (PATCH partial semantics)', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <KindRuleFormDialog
        open
        onOpenChange={vi.fn()}
        initial={LEGACY_ROW}
        kinds={KINDS}
        defaultKindId=""
        onSubmit={onSubmit}
        isSubmitting={false}
        error={null}
      />,
    );

    // Touch an unrelated field only (priority), never the match-type picker.
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const body = onSubmit.mock.calls[0][0];
    expect(body).not.toHaveProperty('match_type');
    // The field the admin actually touched is still sent.
    expect(body.priority).toBe(9);
  });

  it('(c) changing match_type to a known value sends EXACTLY that new value', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <KindRuleFormDialog
        open
        onOpenChange={vi.fn()}
        initial={LEGACY_ROW}
        kinds={KINDS}
        defaultKindId=""
        onSubmit={onSubmit}
        isSubmitting={false}
        error={null}
      />,
    );

    fireEvent.click(screen.getByLabelText('Match type'));
    const option = await screen.findByRole('option', { name: 'Category' });
    fireEvent.click(option);

    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const body = onSubmit.mock.calls[0][0];
    expect(body.match_type).toBe('category');
  });
});
