'use client';

import type { ReactNode } from 'react';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PROJECT_VIEW_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/projectViewPermissions';

export default function ProjectSalesLayout({ children }: { children: ReactNode }) {
  return <RequireAccess permission={PROJECT_VIEW_PERMISSIONS}>{children}</RequireAccess>;
}
