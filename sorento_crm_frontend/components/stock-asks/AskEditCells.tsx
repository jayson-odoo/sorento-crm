'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { STATE_OPTIONS, stateLabel, type StockAsk, type StockAskPatch, type StockAskState } from '@/lib/stock-asks';

/**
 * An ask's State, edited in place (the CRM Asks tab and the portal's Customer asks page).
 * Required, so the select is not clearable. Read-only renders the value where the input
 * would be (view = edit).
 */
export function AskStateCell({
  ask,
  editable,
  onSave,
}: {
  ask: StockAsk;
  editable: boolean;
  onSave: (patch: StockAskPatch) => void;
}) {
  if (!editable) return <span>{stateLabel(ask.state)}</span>;
  const id = `ask-state-${ask.id}`;
  return (
    <>
      <label htmlFor={id} className="sr-only">
        State for {ask.product_code}
      </label>
      <SearchableSelect
        id={id}
        value={ask.state}
        onChange={(v) => {
          if (v && v !== ask.state) onSave({ state: v as StockAskState });
        }}
        options={STATE_OPTIONS}
        size="sm"
      />
    </>
  );
}

/** An ask's Note, edited in place and saved on blur when it changed. */
export function AskNoteCell({
  ask,
  editable,
  onSave,
}: {
  ask: StockAsk;
  editable: boolean;
  onSave: (patch: StockAskPatch) => void;
}) {
  const [draft, setDraft] = useState(ask.note ?? '');
  useEffect(() => setDraft(ask.note ?? ''), [ask.note]);

  if (!editable) {
    return (
      <span className="block truncate" title={ask.note ?? undefined}>
        {ask.note || '-'}
      </span>
    );
  }
  const id = `ask-note-${ask.id}`;
  return (
    <>
      <label htmlFor={id} className="sr-only">
        Note for {ask.product_code}
      </label>
      <Input
        id={id}
        value={draft}
        placeholder="Add a note"
        title={draft || undefined}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          if (draft.trim() !== (ask.note ?? '').trim()) onSave({ note: draft.trim() });
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        }}
        className="h-8"
      />
    </>
  );
}

/**
 * When the ask was made. A chat console hand test (`source = console`) also carries a
 * "Console" badge, so staff never mistake it for a dealer's real ask.
 */
export function AskedAtCell({ ask }: { ask: StockAsk }) {
  const when = formatDateTimeInMalaysia(ask.created_at);
  if (ask.source !== 'console') return <>{when}</>;
  return (
    <span className="flex items-center gap-1.5">
      <span className="truncate">{when}</span>
      <Badge variant="secondary" appearance="light" title="Written by a chat console hand test, not by a dealer">
        Console
      </Badge>
    </span>
  );
}
