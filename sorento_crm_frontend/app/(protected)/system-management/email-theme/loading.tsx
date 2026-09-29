import { SectionSkeleton } from '@/components/common/SectionSkeleton';

/** Held while this form page's chunk and the stored theme arrive (M5-01). */
export default function Loading() {
  return <SectionSkeleton rows={8} />;
}
