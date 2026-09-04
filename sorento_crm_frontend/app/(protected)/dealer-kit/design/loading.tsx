import { SectionSkeleton } from '@/components/common/SectionSkeleton';

/**
 * `dealer-kit/loading.tsx` would otherwise be inherited here (Next.js reuses the
 * nearest ancestor's loading.tsx for a descendant that has none) - the list skeleton
 * up there flashed a table shape over what is a canvas, not a list (M5-01 review S1
 * blast radius).
 */
export default function Loading() {
  return <SectionSkeleton rows={6} />;
}
