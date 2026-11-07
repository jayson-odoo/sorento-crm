import { SectionSkeleton } from '@/components/common/SectionSkeleton';

/**
 * `(view)/loading.tsx` (the Header tab's list skeleton, since the lines grid sits there) would
 * otherwise be inherited here, flashing a table shape over a tab of prose (M5-01 review S1).
 */
export default function Loading() {
  return <SectionSkeleton rows={6} />;
}
