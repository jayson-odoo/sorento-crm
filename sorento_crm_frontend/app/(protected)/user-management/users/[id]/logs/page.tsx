'use client';

import { ContentLoader } from '@/components/common/content-loader';
import { useUser } from '../components/user-context';
import LogList from './components/log-list';

export default function Page() {
  const { isLoading } = useUser();

  return isLoading ? <ContentLoader className="mt-[10%]" /> : <LogList />;
}
