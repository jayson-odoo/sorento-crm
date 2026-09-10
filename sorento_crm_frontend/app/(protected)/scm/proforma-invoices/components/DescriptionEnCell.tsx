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

  useEffect(() => {
    if (!editing) setValue(descriptionEn ?? '');
  }, [descriptionEn, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const editable = canAdjust && !!description?.trim();

  const save = () => {
    const trimmed = value.trim();
    if (!trimmed || trimmed === (descriptionEn ?? '')) {
      setEditing(false);
      setValue(descriptionEn ?? '');
      return;
    }
    mutation.mutate(
      { source_text: description as string, target_text: trimmed },
      { onSuccess: () => setEditing(false) },
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
        className="text-muted-foreground hover:text-foreground hover:underline"
        aria-label={`Add English for ${description}`}
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
