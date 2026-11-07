'use client';

/**
 * The stock inquiry page's ONE tab bar (NPA-FROM-SI, owner hand test 7 Nov: "supposed to be
 * tgt"): `FormDetailTabsWithRevisions` (Details / Comments / Revisions / SLA Tracking) plus
 * "New product applications (N)" for users who hold any application permission. The tab reads
 * the same query the detail's banners read, so it costs no extra request.
 */

import type { ReactNode } from 'react';
import Link from 'next/link';
import FormDetailTabsWithRevisions from '@/app/(protected)/sla-management/_shared/FormDetailTabsWithRevisions';
import type { FormDetailExtraTab } from '@/app/(protected)/sla-management/_shared/FormDetailWithSLATabs';
import { InquiryApplicationsList } from '@/components/common/NewProductApplicationBanners';
import { useHasPermission } from '@/hooks/usePermissions';
import { useStockInquiryApplicationsQuery } from '../../new-product-applications/hooks/useNewProductApplications';

export default function StockInquiryDetailTabs({
  inquiryId,
  children,
}: {
  inquiryId: string;
  children: ReactNode;
}) {
  const canSeeApplications = [
    useHasPermission('procurement.new_product_applications.view'),
    useHasPermission('procurement.new_product_applications.create'),
    useHasPermission('procurement.new_product_applications.approve'),
    useHasPermission('procurement.new_product_applications.open_code'),
  ].some(Boolean);
  const { data: applications } = useStockInquiryApplicationsQuery(inquiryId, canSeeApplications);

  const extraTabs: FormDetailExtraTab[] = canSeeApplications
    ? [
        {
          value: 'applications',
          label: `New product applications (${(applications ?? []).length})`,
          content: (
            <InquiryApplicationsList
              applications={applications ?? []}
              renderNumber={(a) => (
                <Link
                  href={`/procurement-management/new-product-applications/${a.id}`}
                  className="text-primary hover:underline"
                >
                  {a.application_no}
                </Link>
              )}
            />
          ),
        },
      ]
    : [];

  return (
    <FormDetailTabsWithRevisions
      sourceEntityType="stock_inquiry"
      sourceEntityId={inquiryId}
      revisionsKind="stock_inquiry"
      commentsKind="stock_inquiry"
      extraTabs={extraTabs}
    >
      {children}
    </FormDetailTabsWithRevisions>
  );
}
