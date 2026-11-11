'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { AutocountWriteDialog } from './AutocountWriteDialog';
import type { AutocountWriteResult } from '../types/projectAutocountWrite.types';

/**
 * One AutoCount write button and the dialog that shows AutoCount's answer. The caller decides
 * WHETHER it renders (switch, permission, eligibility); this only runs the action and shows the
 * result. A CRM refusal is toasted by the mutation hook, so a rejected run just closes quietly.
 */
export function AutocountWriteButton({
  label,
  pendingLabel,
  run,
  disabled,
  title,
  variant = 'outline',
}: {
  label: string;
  pendingLabel: string;
  run: () => Promise<AutocountWriteResult>;
  disabled?: boolean;
  /** Why it is greyed, shown on hover. */
  title?: string;
  variant?: 'outline' | 'primary';
}) {
  const [pending, setPending] = React.useState(false);
  const [result, setResult] = React.useState<AutocountWriteResult | null>(null);

  const press = async () => {
    setPending(true);
    try {
      setResult(await run());
    } catch {
      // Already toasted by the mutation's onError.
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <Button
        type="button"
        size="sm"
        variant={variant}
        disabled={disabled || pending}
        title={title}
        onClick={press}
      >
        {pending ? pendingLabel : label}
      </Button>
      <AutocountWriteDialog
        open={result !== null}
        onOpenChange={(open) => {
          if (!open) setResult(null);
        }}
        title={label}
        result={result}
        onRetry={press}
        retrying={pending}
      />
    </>
  );
}
