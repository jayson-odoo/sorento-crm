'use client';

import { Badge } from '@/components/ui/badge';

/**
 * The read-only NEW PRODUCT CODE value for the applicant and the portal: the code once purchasing
 * linked it, the reason when it is not opening, otherwise the waiting line. `link` draws the code
 * as a link on the staff side.
 */
export function NewProductApplicationNewCodeValue({
  code,
  active,
  closedReason,
  link,
}: {
  code?: string | null;
  active?: boolean | null;
  closedReason?: string | null;
  link?: React.ReactNode;
}) {
  if (code) {
    return (
      <span className="flex flex-wrap items-center gap-2 font-medium">
        {link ?? code}
        {active === false && <Badge variant="secondary">Inactive</Badge>}
      </span>
    );
  }
  if (closedReason) {
    return <span className="break-words">Not opening: {closedReason}</span>;
  }
  return (
    <p className="text-muted-foreground">
      Purchasing fills this in when the code is created.
    </p>
  );
}
