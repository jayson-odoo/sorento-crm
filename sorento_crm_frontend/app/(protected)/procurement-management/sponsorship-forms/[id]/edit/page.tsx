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
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import PurchaseRequestForm from '../../../purchase-requests/components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'Edit Sponsorship Form',
  description: 'Edit sponsorship form',
};

export default function EditSponsorshipFormPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Container>
      <EditSponsorshipFormWrapper params={params} />
    </Container>
  );
}

async function EditSponsorshipFormWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
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
            <BreadcrumbLink href="/procurement-management/sponsorship-forms">
              Sponsorship Forms
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href={`/procurement-management/sponsorship-forms/${id}`}>
              Details
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Edit</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="mt-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Edit Sponsorship Form</h1>
        <Button variant="outline" asChild>
          <Link href={`/procurement-management/sponsorship-forms/${id}`}>
            Cancel
          </Link>
        </Button>
      </div>
      <div className="mt-6">
        <PurchaseRequestForm
          requestId={id}
          defaultRequestType="sponsorship_form"
          expectedRequestType="sponsorship_form"
          successRedirectUrl={`/procurement-management/sponsorship-forms/${id}`}
        />
      </div>
    </>
  );
}
