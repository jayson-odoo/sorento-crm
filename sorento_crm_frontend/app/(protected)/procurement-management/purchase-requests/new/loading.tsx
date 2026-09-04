import { SectionSkeleton } from '@/components/common/SectionSkeleton';

/**
 * Held while this segment's chunk arrives (M5-01 run 3). `PurchaseRequestForm`
 * embeds a line-items DataGrid as one section of a multi-field form, not the
 * whole page - the full `ListPageSkeleton` table shape would misrepresent a
 * form. The page draws its own `PageHeader` directly (no parent layout owns
 * it here, and it is not headerless either).
 */
export default function Loading() {
  return <SectionSkeleton rows={6} />;
}
