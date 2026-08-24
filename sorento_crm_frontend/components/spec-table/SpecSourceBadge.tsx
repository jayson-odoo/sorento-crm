'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { cn } from '@/lib/utils';

/**
 * Where a value came from, and - one tap away - the words it came from.
 *
 * The evidence is never a column of its own (D6). A permanent column of
 * "WASHDOWN WITH RIMLESS. D: L680xW375xH770MM" pushes the value itself off the right
 * of a phone and makes the table unreadable at the width most of its readers are on.
 *
 * It is behind BOTH a hover title and a tap-to-expand strip, and that is not
 * belt-and-braces: `title` does not exist on a touch device, so hover alone would put
 * the only justification for a machine-read value out of reach at 375px.
 */

/**
 * Provenance sources mapped onto the shared pill vocabulary, locally.
 *
 * A local map rather than new entries in `lib/status-pill.ts`: `flyer` and `category`
 * are words from one domain, and the shared cross-domain vocabulary is not the place
 * to put them. A person's own word takes `manual`'s affirmative blue; every machine
 * reading takes `ai`'s muted grey, because that is the distinction being drawn.
 */
const SOURCE_PILL_KEY: Record<string, string> = {
  human: 'manual',
  supplier: 'manual',
  derived: 'ai',
  rule: 'ai',
  flyer: 'ai',
  code: 'ai',
  category: 'ai',
};

/** Named the way the person reading it would name it, not the way it is stored. */
export const SOURCE_LABEL: Record<string, string> = {
  derived: 'Description',
  rule: 'Description',
  flyer: 'Flyer',
  code: 'Product code',
  category: 'Category',
  human: 'Set by hand',
  supplier: 'Supplier',
};

/** Authored sources, mirroring the backend `AUTHORED_SOURCES` constant. */
const AUTHORED_SOURCES = new Set(['human', 'supplier']);

export function SpecSourceBadge({
  source,
  evidence,
  migratedFrom = null,
  className,
}: {
  source: string | null;
  evidence: string | null;
  /**
   * What an authored value was before it was authored - `flyer` on a promoted one.
   *
   * It changes no pill and no label: a promoted value IS authored now, it wins every
   * conflict a typed one wins, and inventing a fourth colour for it would be a state
   * to learn for a distinction that has no consequence. What it changes is the one
   * word in front of the evidence, because "Set by: flyer: Matt Black finish" claims
   * a person wrote a sentence that was quoted off a printed flyer (AC-B.15).
   */
  migratedFrom?: string | null;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  if (!source) {
    return <span className={cn('text-xs text-muted-foreground', className)}> - </span>;
  }

  const label = SOURCE_LABEL[source] ?? source;
  const authored = AUTHORED_SOURCES.has(source) && !migratedFrom;
  // "Set by tehjayson@..." is an audit stamp, not a quotation from a document, and
  // labelling it "Read from" would claim the person's name appears in the catalogue.
  // A promoted value is the other way round: authored, but the evidence really is a
  // quotation, and it already reads "flyer: ...".
  const evidenceLabel = authored ? 'Set by' : 'Read from';

  return (
    <div className={cn('flex min-w-0 flex-col gap-1', className)}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        disabled={!evidence}
        aria-expanded={evidence ? open : undefined}
        aria-label={evidence ? `${evidenceLabel}: ${evidence}` : label}
        title={evidence ? `${evidenceLabel}: ${evidence}` : undefined}
        className="flex w-fit max-w-full items-center gap-1 disabled:cursor-default"
        data-spec-source={source}
        data-spec-migrated-from={migratedFrom ?? undefined}
      >
        <span className={cn(STATUS_PILL_BASE, statusPillClass(SOURCE_PILL_KEY[source] ?? 'ai'))}>
          {label}
        </span>
        {evidence && (
          <ChevronDown
            className={cn('size-3 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')}
          />
        )}
      </button>
      {open && evidence && (
        <p
          className="rounded-md border bg-muted/30 p-2 font-mono text-[11px] leading-snug break-words whitespace-pre-wrap text-muted-foreground"
          data-spec-evidence={source}
        >
          <span className="font-sans font-medium">{evidenceLabel}: </span>
          {evidence}
        </p>
      )}
    </div>
  );
}
