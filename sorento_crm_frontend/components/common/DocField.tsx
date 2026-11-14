'use client';

/**
 * One field of a paper-form document card (the sample request shell, also the order change
 * notice): a muted label, the control or read-only value under it, and its own message beside
 * it. Shared so the two forms draw the same document.
 */

import type { ReactNode } from 'react';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

export function DocField({
  label,
  htmlFor,
  className,
  error,
  children,
}: {
  label: string;
  htmlFor?: string;
  className?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('min-w-0', className)}>
      {htmlFor ? (
        <Label htmlFor={htmlFor} className="text-sm font-normal text-muted-foreground">
          {label}
        </Label>
      ) : (
        <p className="text-sm text-muted-foreground">{label}</p>
      )}
      <div className="mt-1.5">{children}</div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

/** A read-only value in a document card; a dash when there is none. */
export const ReadValue = ({ children }: { children: ReactNode }) => (
  <p className="min-h-9 break-words py-2 text-sm">{children || '-'}</p>
);
