'use client';

import type { ReactNode } from 'react';
import RequireAccess from '@/app/components/common/RequireAccess';

export default function DealerKitLayout({ children }: { children: ReactNode }) {
  return <RequireAccess permission="dealer_kit.page.view">{children}</RequireAccess>;
}
