'use client';

import type { ReactNode } from 'react';
import RequireAccess from '@/app/components/common/RequireAccess';

export default function ScmLayout({ children }: { children: ReactNode }) {
  return <RequireAccess permission="scm.dashboard.view">{children}</RequireAccess>;
}
