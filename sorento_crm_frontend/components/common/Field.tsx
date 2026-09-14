'use client';

import { Label } from '@/components/ui/label';

/**
 * One label/value pair on a record's General tab.
 *
 * Lifted out of `ProformaInvoiceDetail` (S3 of the 14 Sep SCM feedback batch) when the
 * loading plan grew a General tab of its own: two records rendering the same pair from two
 * private copies is two places for the label scale to drift. `htmlFor` is what an edit-mode
 * field passes so its label points at the input that replaced the value; a read-only pair
 * has nothing to point at and renders a plain span.
 */
export function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      {htmlFor ? (
        <Label className="text-xs font-normal text-muted-foreground" htmlFor={htmlFor}>
          {label}
        </Label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export default Field;
