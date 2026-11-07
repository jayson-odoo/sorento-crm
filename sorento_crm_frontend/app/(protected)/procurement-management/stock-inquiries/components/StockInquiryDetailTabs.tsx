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
  const { data: applications, isError } = useStockInquiryApplicationsQuery(inquiryId, canSeeApplications);

  const extraTabs: FormDetailExtraTab[] = canSeeApplications
    ? [
        {
          value: 'applications',
          // A failed read says so: never "(0)" and the empty state, which would read as "none".
          label:
            isError || applications === undefined
              ? 'New product applications'
              : `New product applications (${applications.length})`,
          content: applications === undefined && !isError ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Loading...</p>
          ) : isError ? (
            <p role="alert" className="py-6 text-center text-sm text-destructive">
              Could not load the new product applications.
            </p>
          ) : (
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
