'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PROJECT_VIEW_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/projectViewPermissions';
import { SPARE_PART_CREATE_PERMISSION } from '@/app/(protected)/project-sales/_shared/lib/sparePartRequest';

/** SPARE-PART-ORDER-REQUEST (B1): a spare part requester's screens are the Order Inquiries list,
 *  the request form and the OI page; the server scopes every read to their own requests. */
const ORDER_INQUIRIES = '/project-sales/order-inquiries';
const ORDER_INQUIRY_PERMISSIONS = [...PROJECT_VIEW_PERMISSIONS, SPARE_PART_CREATE_PERMISSION];

/** Project import (`/project-sales/import`) has its own grant: an import-only user reaches it,
 *  and only it. Every other Project Sales page keeps the project read gate. */
const IMPORT_PATH = '/project-sales/import';
const IMPORT_PERMISSIONS = ['projects.import.view'];

export default function ProjectSalesLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  const orderInquiries = pathname === ORDER_INQUIRIES || pathname.startsWith(`${ORDER_INQUIRIES}/`);
  const isImport = pathname === IMPORT_PATH || pathname.startsWith(`${IMPORT_PATH}/`);
  const permissions = isImport
    ? IMPORT_PERMISSIONS
    : orderInquiries
      ? ORDER_INQUIRY_PERMISSIONS
      : PROJECT_VIEW_PERMISSIONS;
  return (
    <RequireAccess anyPermission={permissions}>
      {children}
    </RequireAccess>
  );
}
