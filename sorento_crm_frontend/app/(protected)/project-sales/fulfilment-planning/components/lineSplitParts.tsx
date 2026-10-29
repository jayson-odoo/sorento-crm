'use client';

import * as React from 'react';
import { Input } from '@/components/ui/input';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { OrderInquiryVerbPill } from '../../_shared/components/OrderInquiryVerbPill';
import type { ChangeWord } from '../lib/lineSplitModel';

/** The change pill, in the verb colours the OI screens already use (UAC A11). */
export function ChangePill({ word }: { word: ChangeWord }) {
  if (word === 'CANCEL')
    return (
      <span
        className={`${STATUS_PILL_BASE} normal-case ${statusPillClass('rejected')}`}
      >
        CANCEL
      </span>
    );
  return <OrderInquiryVerbPill verb={word} />;
}

/**
 * A whole-number qty typed as text, `inputMode` numeric for the phone keypad. It may be
 * emptied while typing (NUMBER-FIELDS): nothing rewrites the box, an empty box counts as 0,
 * and a zero split is dropped when focus leaves its line (UAC A4).
 */
export function QtyInput({
  value,
  onValue,
  ...props
}: Omit<
  React.ComponentProps<typeof Input>,
  'value' | 'onChange' | 'type' | 'inputMode'
> & {
  value: number;
  onValue: (qty: number) => void;
}) {
  const [draft, setDraft] = React.useState(() => String(value));
  // The sheet moved the qty itself (a drop, an undo): the figure replaces the typed text.
  if ((draft === '' ? 0 : Number(draft)) !== value) setDraft(String(value));
  return (
    <Input
      {...props}
      type="text"
      inputMode="numeric"
      autoComplete="off"
      value={draft}
      onChange={(event) => {
        const digits = event.target.value.replace(/\D/g, '');
        setDraft(digits);
        onValue(digits === '' ? 0 : Number(digits));
      }}
    />
  );
}
