'use client';

import { Info } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

export interface FormulaTerm {
  /** The symbol as it appears in the formula line. */
  name: string;
  /** Weight or coefficient, when the formula has one. */
  weight?: string;
  /** Where the figure comes from, in a few words. */
  note: string;
}

/**
 * A column header's "how is this worked out": the formula as a formula, then one line per
 * term, then the footnote. Structured rather than a sentence so the eye lands on the
 * arithmetic first and reads the definitions only when it wants them (captain, 27 Aug).
 */
export function FormulaTip({
  label,
  formula,
  terms,
  footer,
}: {
  label: string;
  formula: string;
  terms: FormulaTerm[];
  footer?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          aria-label={label}
          className="inline-flex cursor-help items-center text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Info className="size-3.5" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-sm space-y-2 p-3">
        <code className="block rounded bg-muted px-2 py-1 font-mono text-xs text-foreground">
          {formula}
        </code>
        <dl className="grid grid-cols-[auto_auto_1fr] gap-x-3 gap-y-1 text-xs">
          {terms.map((t) => (
            <div key={t.name} className="contents">
              <dt className="font-medium">{t.name}</dt>
              <dd className="tabular-nums text-muted-foreground">{t.weight ?? ''}</dd>
              <dd className="text-muted-foreground">{t.note}</dd>
            </div>
          ))}
        </dl>
        {footer ? <p className="text-2xs text-muted-foreground">{footer}</p> : null}
      </TooltipContent>
    </Tooltip>
  );
}

export default FormulaTip;
