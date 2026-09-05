'use client';

import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { useUser } from '../components/user-context';
import LogList from './components/log-list';

export default function Page() {
  const { isLoading } = useUser();

  return isLoading ? (
    <SectionSkeleton rows={3} className="mx-auto max-w-md mt-[10%]" />
  ) : (
    <LogList />
  );
}
