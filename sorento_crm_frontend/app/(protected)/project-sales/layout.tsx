'use client';

import type { ReactNode } from 'react';
import RequireAccess from '@/app/components/common/RequireAccess';

export default function ProjectSalesLayout({ children }: { children: ReactNode }) {
  return <RequireAccess permission="projects.projects.view">{children}</RequireAccess>;
}
