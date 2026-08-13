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
import PurchaseRequestDetail from '../../purchase-requests/components/PurchaseRequestDetail';
import FormDetailTabsWithRevisions from '@/app/(protected)/sla-management/_shared/FormDetailTabsWithRevisions';
import RecordEntityRegistrar from '@/components/common/RecordEntityRegistrar';

export const metadata: Metadata = {
  title: 'Sponsorship Form Details',
  description: 'View sponsorship form details',
};

export default function SponsorshipFormDetailPage({
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
            <BreadcrumbPage>Project Sales Admin</BreadcrumbPage>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href="/procurement-management/sponsorship-forms">
              Sponsorship Forms
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Details</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="mt-6">
        <SponsorshipFormDetailWrapper params={params} />
      </div>
    </Container>
  );
}

async function SponsorshipFormDetailWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <FormDetailTabsWithRevisions
      sourceEntityType="sponsorship_form"
      sourceEntityId={id}
      revisionsKind="sponsorship_form"
    >
      <RecordEntityRegistrar entityType="sponsorship_form" id={id} />
      <PurchaseRequestDetail
        requestId={id}
        basePath="/procurement-management/sponsorship-forms"
      />
    </FormDetailTabsWithRevisions>
  );
}
