import { SectionSkeleton } from '@/components/common/SectionSkeleton';

/**
 * Held while this segment's chunk arrives (M5-01). The edit page is the customer
 * form with an Asks tab that holds a DataGrid (chatbot stock ask v2 S5), not a
 * list page - the full `ListPageSkeleton` table shape would misrepresent a form.
 * The page draws its own `PageHeader` directly.
 */
export default function Loading() {
  return <SectionSkeleton rows={6} />;
}
