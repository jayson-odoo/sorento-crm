'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PROJECT_VIEW_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/projectViewPermissions';

/** Project import (`/project-sales/import`) has its own grant: an import-only user reaches it,
 *  and only it. Every other Project Sales page keeps the project read gate. */
const IMPORT_PATH = '/project-sales/import';
const IMPORT_PERMISSIONS = ['projects.import.view'];

export default function ProjectSalesLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  const isImport = pathname === IMPORT_PATH || pathname.startsWith(`${IMPORT_PATH}/`);
  return (
    <RequireAccess anyPermission={isImport ? IMPORT_PERMISSIONS : PROJECT_VIEW_PERMISSIONS}>
      {children}
    </RequireAccess>
  );
}
