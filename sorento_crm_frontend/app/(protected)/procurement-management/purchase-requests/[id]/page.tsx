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
import BackToList from '@/components/common/BackToList';
import PurchaseRequestDetail from '../components/PurchaseRequestDetail';
import FormDetailTabsWithRevisions from '@/app/(protected)/sla-management/_shared/FormDetailTabsWithRevisions';
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/">Home</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Project Sales Admin</BreadcrumbPage>
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
        <BackToList
          listPath="/procurement-management/purchase-requests"
          label="Back to purchase requests"
        />
      </div>
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
    <FormDetailTabsWithRevisions
      sourceEntityType="purchase_request"
      sourceEntityId={id}
      revisionsKind="purchase_request"
    >
      <RecordEntityRegistrar entityType="purchase_request" id={id} />
      <PurchaseRequestDetail requestId={id} />
    </FormDetailTabsWithRevisions>
  );
}
