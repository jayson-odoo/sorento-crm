'use client';

import { useEffect, useRef, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { EM_DASH } from '../../lib/format';
import { useProformaInvoiceTranslationMutation } from '../../hooks/useProformaInvoiceTranslation';

/**
 * `Description (EN)` (S2, AC-E1-E3): the English cell shared by the Packing tab and the
 * Lines tab (view AND edit mode, same position - it is not part of the line form, it
 * writes the glossary directly).
 *
 * A dash for a description the glossary has never seen, including an already-English
 * one (R7 - no auto-mirror, one rule, nothing guessed). `canAdjust` and a non-empty
 * `description` are both required to edit - a row with nothing in `description` has
 * nothing to key the glossary entry on.
 */
export function DescriptionEnCell({
  invoiceId,
  description,
  descriptionEn,
  canAdjust,
}: {
  invoiceId: string;
  description: string | null;
  descriptionEn: string | null;
  canAdjust: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(descriptionEn ?? '');
  const inputRef = useRef<HTMLInputElement>(null);
  const mutation = useProformaInvoiceTranslationMutation(invoiceId);
  // Enter saves and, on success, swaps this `<Input>` for the read-mode button - which
  // removes a still-focused element from the DOM and makes the browser fire a real `blur`
  // on it as part of that removal, replaying `onBlur={save}` a second time with the SAME
  // (already-saved) value before React finishes unmounting. Guards the one real request
  // per edit session - but ONLY until that request settles: reset on the editing effect
  // alone left a FAILED save dead forever (`editing` never flips to unset it, so neither
  // Enter nor blur could ever try again). Reset in `onSettled` below instead, which fires
  // on both outcomes; the editing-start reset stays too, for the ordinary case of opening
  // a fresh edit on a row that never failed.
  const savingRef = useRef(false);

  useEffect(() => {
    if (!editing) setValue(descriptionEn ?? '');
  }, [descriptionEn, editing]);

  useEffect(() => {
    if (editing) {
      savingRef.current = false;
      inputRef.current?.focus();
    }
  }, [editing]);

  const editable = canAdjust && !!description?.trim();

  const save = () => {
    if (savingRef.current) return;
    const trimmed = value.trim();
    if (!trimmed || trimmed === (descriptionEn ?? '')) {
      setEditing(false);
      setValue(descriptionEn ?? '');
      return;
    }
    savingRef.current = true;
    mutation.mutate(
      { source_text: description as string, target_text: trimmed },
      {
        onSuccess: () => setEditing(false),
        // A failed save leaves the cell live (`editing` stays true) - the toast already
        // names the error; keep the input focused rather than let whatever the blur
        // moved focus to win instead.
        onError: () => inputRef.current?.focus(),
        onSettled: () => {
          savingRef.current = false;
        },
      },
    );
  };

  const cancel = () => {
    setValue(descriptionEn ?? '');
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <Input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              save();
            } else if (e.key === 'Escape') {
              e.preventDefault();
              cancel();
            }
          }}
          disabled={mutation.isPending}
          aria-label={`English for ${description}`}
          className="h-8"
        />
        {mutation.isPending ? <LoaderCircle className="size-3.5 animate-spin text-muted-foreground" /> : null}
      </div>
    );
  }

  if (!descriptionEn) {
    return editable ? (
      <button
        type="button"
        onClick={() => setEditing(true)}
        // A rest-state affordance, not just a hover one - a dash under a `Description`
        // full of real text otherwise reads as "nothing here" rather than "click to add
        // one" (review round, 10 Sep).
        className="text-muted-foreground underline decoration-dashed underline-offset-2 hover:text-foreground"
        aria-label={`Add English for ${description}`}
        title={`Add English for ${description}`}
      >
        {EM_DASH}
      </button>
    ) : (
      <span className="text-muted-foreground">{EM_DASH}</span>
    );
  }

  return editable ? (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="block max-w-full truncate text-left hover:underline"
      title={descriptionEn}
    >
      {descriptionEn}
    </button>
  ) : (
    <span className="block truncate" title={descriptionEn}>
      {descriptionEn}
    </span>
  );
}

export default DescriptionEnCell;
