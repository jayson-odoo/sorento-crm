'use client';

/**
 * SAMPLE-FROM-QUOTE: the quotation picker (only when the project has more than one quotation
 * document) and the one-line note naming quotation lines that did not become rows. Rendered above
 * and below the items table of both sample request forms, from `useSampleRequestPrefill`.
 */
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SampleRequestQuotationOption } from '@/types/sampleRequest';

export function SampleRequestQuotationPicker({
  documents,
  value,
  onPick,
  disabled,
}: {
  documents: SampleRequestQuotationOption[];
  /** The document the rows came from (or the server's default). */
  value: string;
  onPick: (documentId: string) => void;
  disabled?: boolean;
}) {
  if (documents.length < 2) return null;
  const options = documents.map((d) => ({ value: d.id, label: d.label }));
  return (
    <div className="min-w-0 space-y-1.5 sm:max-w-sm">
      <Label htmlFor="sr-quotation">Quotation</Label>
      <SearchableSelect
        id="sr-quotation"
        value={value}
        onChange={(v) => v && onPick(v)}
        options={options}
        selectedOption={options.find((o) => o.value === value)}
        disabled={disabled}
        truncateTriggerLabel
      />
    </div>
  );
}

export function SampleRequestPrefillNote({ note }: { note: string | null }) {
  if (!note) return null;
  return <p className="text-sm text-muted-foreground">{note}</p>;
}
