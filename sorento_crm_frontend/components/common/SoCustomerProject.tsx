import { cn } from '@/lib/utils';

/**
 * OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 19:35): wherever a sales order is named, its customer and
 * project are named with it, in ONE format: `CUSTOMER / project`. The two halves are the SO
 * list's own Customer and Project fields (`customer_name`, `project_label`); a missing half
 * prints a dash in its place (AC-6), so a lone project never reads as the customer. Never an id.
 */
export function soCustomerProjectLabel(
  customer: string | null | undefined,
  project: string | null | undefined,
): string | null {
  const [c, p] = [customer, project].map((part) => (part ?? '').trim());
  return c || p ? `${c || '-'} / ${p || '-'}` : null;
}

/** The one-line `CUSTOMER / project` under or beside an SO number. Truncates, full text in
 *  its title. Renders nothing when neither half is known, unless `emptyText` is given. */
export function SoCustomerProject({
  customer,
  project,
  emptyText,
  className,
}: {
  customer: string | null | undefined;
  project: string | null | undefined;
  emptyText?: string;
  className?: string;
}) {
  const label = soCustomerProjectLabel(customer, project);
  if (!label) {
    return emptyText ? (
      <span className={cn('block truncate text-xs text-muted-foreground', className)}>
        {emptyText}
      </span>
    ) : null;
  }
  return (
    <span className={cn('block truncate text-xs text-muted-foreground', className)} title={label}>
      {label}
    </span>
  );
}
