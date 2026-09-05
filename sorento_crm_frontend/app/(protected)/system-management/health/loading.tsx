import { SectionSkeleton } from '@/components/common/SectionSkeleton';

/**
 * Held while this segment's chunk arrives (M5-01 run 3). `HealthDashboard`
 * is a stack of status cards - the Integrations card's DataGrid is one
 * section among several, not the whole page - so the generic bar shape
 * fits better than the 10-row list table. The page draws its own
 * `PageHeader` directly (no parent layout owns it here, and it is not
 * headerless either).
 */
export default function Loading() {
  return <SectionSkeleton rows={6} />;
}
