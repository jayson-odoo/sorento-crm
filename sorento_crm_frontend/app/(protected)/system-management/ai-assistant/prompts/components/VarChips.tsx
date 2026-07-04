'use client';

import { Badge } from '@/components/ui/badge';
import type { VarValidation } from '../../lib/promptVars';

/**
 * Green = declared var present, amber = declared-but-missing (soft warn),
 * red inline error lists unknown tokens (hard block). PLAN §9b Q7.
 */
export function VarChips({ validation, declared }: { validation: VarValidation; declared: string[] }) {
  if (declared.length === 0 && validation.unknown.length === 0) {
    return <p className="text-xs text-muted-foreground">This prompt declares no variables.</p>;
  }
  return (
    <div className="space-y-2" data-testid="var-chips">
      <div className="flex flex-wrap items-center gap-1.5">
        {declared.map((v) => {
          const missing = validation.missing.includes(v);
          return (
            <Badge
              key={v}
              variant={missing ? 'warning' : 'success'}
              className="font-mono text-xs"
              data-testid={`var-chip-${v}`}
              data-state={missing ? 'missing' : 'present'}
            >
              {`{{${v}}}`}
              {missing ? ' — missing' : ''}
            </Badge>
          );
        })}
      </div>
      {validation.missing.length > 0 ? (
        <p className="text-xs text-amber-600" data-testid="var-missing-warning">
          Warning: declared variable(s) not used in the template — {validation.missing.join(', ')}. Save is still
          allowed, but the substitution will have nothing to fill.
        </p>
      ) : null}
      {validation.unknown.length > 0 ? (
        <p className="text-xs text-destructive" data-testid="var-unknown-error">
          Unknown token(s): {validation.unknown.map((t) => `{{${t}}}`).join(', ')}. These are not declared for this
          prompt and would leak literally — remove them before saving.
        </p>
      ) : null}
    </div>
  );
}
