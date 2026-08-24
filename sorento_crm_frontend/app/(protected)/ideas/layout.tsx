'use client';

import type { ReactNode } from 'react';
import RequireAccess from '@/app/components/common/RequireAccess';

export default function IdeasLayout({ children }: { children: ReactNode }) {
  return <RequireAccess permission="ideation.board.view">{children}</RequireAccess>;
}
