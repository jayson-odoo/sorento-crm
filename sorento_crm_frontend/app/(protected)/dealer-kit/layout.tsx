'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import RequireAccess from '@/app/components/common/RequireAccess';

const PAGE_VIEW = 'dealer_kit.page.view';

/**
 * The price tag request table and request page (not the designer) also open for a salesperson's
 * own requests (PORTAL-P4-REQUESTS S7); the server narrows them to their own rows.
 */
const OWN_PRICE_TAG_PAGE = /^\/dealer-kit\/price-tag-requests(\/[^/]+)?\/?$/;
const OWN_PRICE_TAG_ACCESS = [PAGE_VIEW, 'dealer_kit.price_tag_requests.view_own'] as const;

export default function DealerKitLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  if (OWN_PRICE_TAG_PAGE.test(pathname)) {
    return <RequireAccess anyPermission={[...OWN_PRICE_TAG_ACCESS]}>{children}</RequireAccess>;
  }
  return <RequireAccess permission={PAGE_VIEW}>{children}</RequireAccess>;
}
