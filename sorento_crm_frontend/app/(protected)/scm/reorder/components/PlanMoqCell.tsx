'use client';

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { EM_DASH, fmtInt } from '../../lib/format';

/**
 * The MoQ a buy/covered row was actually rounded against - editable in place (20 Aug live
 * test, captain).
 *
 * > "user feedback that MoQ is varying from time to time so they don't maintain it, so we
 * >  need a place for the user to input MoQ in this table, we can default from master data
 * >  but allow change, and when they change, our calculation should recalculate"
 *
 * Defaults to the frozen master figure (`product_suppliers.moq` at run time). Typing a new
 * number overrides it for this row - or, on a grouped PRODUCT row, every location it
 * summed (MOQ is a supplier/product fact, not a per-location one - captain's 20 Aug
 * ruling, `planLineGrouping.ts`). Clearing the field back to empty withdraws the override
 * and falls back to the master figure again. `master N` shows underneath ONLY while
 * overridden, so the row never hides what master data actually says.
 */
export function PlanMoqCell({
  moq,
  masterMoq,
  isOverride,
  onChange,
  disabled,
  note,
}: {
  /** The MoQ the row's `order_qty` was rounded against - the override when set, else the
   *  frozen master figure. */
  moq: number | null;
  /** The frozen master figure, even while overridden - shown as "master N" underneath. */
  masterMoq: number | null;
  isOverride: boolean;
  /** Record (or withdraw, with null) the buyer's own MoQ. Absent/undefined = read-only. */
  onChange?: (value: number | null) => Promise<void> | void;
  disabled?: boolean;
  /** The sell-through warning when the MOQ pumps the buy above need (`moqGap`). */
  note?: { text: string; warn: boolean; title: string } | null;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!onChange || disabled) {
    return moq === null ? (
      <span className="text-muted-foreground" title="No MOQ on file for this supplier">
        {EM_DASH}
      </span>
    ) : (
      <div className="min-w-0">
        <span className="tabular-nums">{fmtInt(moq)}</span>
        {note ? (
          <span
            className={`block truncate text-2xs ${note.warn ? 'text-scm-overstock' : 'text-muted-foreground'}`}
            title={note.title}
          >
            {note.text}
          </span>
        ) : null}
      </div>
    );
  }

  const value = draft ?? (moq === null ? '' : String(moq));

  const commit = async () => {
    if (draft === null) return; // untouched - nothing to save
    const trimmed = draft.trim();
    if (trimmed === '') {
      setSaving(true);
      try {
        await onChange(null);
      } finally {
        setSaving(false);
        setDraft(null);
      }
      return;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    // Typing the master figure back is a withdrawal, not an override.
    setSaving(true);
    try {
      await onChange(parsed === masterMoq ? null : parsed);
    } finally {
      setSaving(false);
      setDraft(null);
    }
  };

  return (
    <div className="min-w-0">
      <Input
        type="number"
        min={0}
        inputMode="decimal"
        className="h-7 w-20 tabular-nums"
        aria-label="MOQ"
        placeholder={masterMoq === null ? undefined : String(masterMoq)}
        value={value}
        disabled={saving}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur();
        }}
      />
      {isOverride ? (
        <span
          className="mt-0.5 block truncate text-2xs text-muted-foreground"
          title={masterMoq === null ? 'No master MOQ on file' : `Master MOQ: ${masterMoq}`}
        >
          {masterMoq === null ? 'edited' : `master ${masterMoq}`}
        </span>
      ) : note ? (
        <span
          className={`block truncate text-2xs ${note.warn ? 'text-scm-overstock' : 'text-muted-foreground'}`}
          title={note.title}
        >
          {note.text}
        </span>
      ) : null}
    </div>
  );
}
