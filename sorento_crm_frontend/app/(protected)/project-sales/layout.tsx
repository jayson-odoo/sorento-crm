'use client';

import type { ReactNode } from 'react';
import RequireAccess from '@/app/components/common/RequireAccess';

const PROJECT_VIEW_PERMISSIONS = ['projects.projects.view', 'projects.projects.view_own'];

export default function ProjectSalesLayout({ children }: { children: ReactNode }) {
  return <RequireAccess permission={PROJECT_VIEW_PERMISSIONS}>{children}</RequireAccess>;
}
