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
import PurchaseRequestDetail from '../components/PurchaseRequestDetail';
import FormDetailWithSLATabs from '@/app/(protected)/sla-management/_shared/FormDetailWithSLATabs';
import RecordEntityRegistrar from '@/components/common/RecordEntityRegistrar';

export const metadata: Metadata = {
  title: 'Purchase Request Details',
  description: 'View purchase request or sponsorship form details',
};

export default function PurchaseRequestDetailPage({
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
            <BreadcrumbLink href="/procurement-management/purchase-requests">
              Purchase Requests
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Details</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="mt-6">
        <PurchaseRequestDetailWrapper params={params} />
      </div>
    </Container>
  );
}

async function PurchaseRequestDetailWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <FormDetailWithSLATabs sourceEntityType="purchase_request" sourceEntityId={id}>
      <RecordEntityRegistrar entityType="purchase_request" id={id} />
      <PurchaseRequestDetail requestId={id} />
    </FormDetailWithSLATabs>
  );
}
