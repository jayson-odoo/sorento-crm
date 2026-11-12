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

export default function ProjectSalesLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  const orderInquiries = pathname === ORDER_INQUIRIES || pathname.startsWith(`${ORDER_INQUIRIES}/`);
  return (
    <RequireAccess anyPermission={orderInquiries ? ORDER_INQUIRY_PERMISSIONS : PROJECT_VIEW_PERMISSIONS}>
      {children}
    </RequireAccess>
  );
}
