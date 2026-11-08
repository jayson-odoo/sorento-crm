'use client';

import { use } from 'react';
import NewProductApplicationForm from '../../components/NewProductApplicationForm';

// Legacy slug-less tree: without this route `/portal/new_product_application/new` fell through to the
// generic [type] page and 404'd, because new_product_application is not a generic submission kind.
// `?stock_inquiry_id=` starts the application from that inquiry (the inquiry view's Create button).
export default function PortalNewProductApplicationNewPage({
  searchParams,
}: {
  searchParams: Promise<{ stock_inquiry_id?: string }>;
}) {
  const { stock_inquiry_id } = use(searchParams);
  return <NewProductApplicationForm startFromInquiryId={stock_inquiry_id} />;
}
