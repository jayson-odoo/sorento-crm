'use client';

import { Badge } from '@/components/ui/badge';

/**
 * The read-only NEW PRODUCT CODE value for the applicant and the portal: the code once purchasing
 * linked it, "Rejected: <reason>" for an older Not opening result, otherwise the waiting line. `link` draws the code
 * as a link on the staff side.
 */
export function NewProductApplicationNewCodeValue({
  code,
  active,
  closedReason,
  supplier,
  link,
}: {
  code?: string | null;
  active?: boolean | null;
  closedReason?: string | null;
  /** The portal's one read-out of the linked product (PQ1). */
  supplier?: string | null;
  link?: React.ReactNode;
}) {
  if (code) {
    return (
      <div className="min-w-0 space-y-0.5">
        <span className="flex flex-wrap items-center gap-2 font-medium">
          {link ?? code}
          {active === false && <Badge variant="secondary">Inactive</Badge>}
        </span>
        {supplier && (
          <p className="text-xs text-muted-foreground">Supplier: {supplier}</p>
        )}
      </div>
    );
  }
  if (closedReason) {
    return <span className="break-words">Rejected: {closedReason}</span>;
  }
  return (
    <p className="text-muted-foreground">
      Purchasing fills this in when the code is created.
    </p>
  );
}
