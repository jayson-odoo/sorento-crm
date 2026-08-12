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
import PurchaseRequestForm from '../components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'New Purchase Request',
  description: 'Create a purchase request or sponsorship form',
};

export default function NewPurchaseRequestPage() {
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
            <BreadcrumbLink href="/procurement-management/purchase-requests">
              Purchase Requests
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>New</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="mt-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">New Purchase Request</h1>
        <Button variant="outline" asChild>
          <Link href="/procurement-management/purchase-requests">Cancel</Link>
        </Button>
      </div>
      <div className="mt-6">
        <PurchaseRequestForm
          successRedirectUrl="/procurement-management/purchase-requests"
        />
      </div>
    </Container>
  );
}
