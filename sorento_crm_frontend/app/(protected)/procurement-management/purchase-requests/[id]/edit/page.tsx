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
import PurchaseRequestForm from '../../components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'Edit Purchase Request',
  description: 'Edit purchase request or sponsorship form',
};

export default function EditPurchaseRequestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Container>
      <EditPurchaseRequestWrapper params={params} />
    </Container>
  );
}

async function EditPurchaseRequestWrapper({
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
            <BreadcrumbLink href={`/procurement-management/purchase-requests/${id}`}>
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
        <h1 className="text-2xl font-bold">Edit Purchase Request</h1>
        <Button variant="outline" asChild>
          <Link href={`/procurement-management/purchase-requests/${id}`}>
            Cancel
          </Link>
        </Button>
      </div>
      <div className="mt-6">
        <PurchaseRequestForm
          requestId={id}
          expectedRequestType="purchase_request"
          successRedirectUrl={`/procurement-management/purchase-requests/${id}`}
        />
      </div>
    </>
  );
}
