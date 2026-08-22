import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import StockInquiryDetail from '../components/StockInquiryDetail';
import FormDetailTabsWithRevisions from '@/app/(protected)/sla-management/_shared/FormDetailTabsWithRevisions';
import RecordEntityRegistrar from '@/components/common/RecordEntityRegistrar';

export const metadata: Metadata = {
  title: 'Stock Inquiry Details',
  description: 'View stock inquiry details',
};

export default function StockInquiryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Container>
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/">Home</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href="/procurement-management">Procurement</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href="/procurement-management/stock-inquiries">
              Stock Inquiries
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Details</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="mt-6">
        <StockInquiryDetailWrapper params={params} />
      </div>
    </Container>
  );
}

async function StockInquiryDetailWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <FormDetailTabsWithRevisions
      sourceEntityType="stock_inquiry"
      sourceEntityId={id}
      revisionsKind="stock_inquiry"
    >
      <RecordEntityRegistrar entityType="stock_inquiry" id={id} />
      <StockInquiryDetail inquiryId={id} />
    </FormDetailTabsWithRevisions>
  );
}
