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
import PurchaseRequestForm from '../../purchase-requests/components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'New Sponsorship Form',
  description: 'Create a sponsorship form',
};

export default function NewSponsorshipFormPage() {
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
            <BreadcrumbPage>New</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="mt-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">New Sponsorship Form</h1>
        <Button variant="outline" asChild>
          <Link href="/procurement-management/sponsorship-forms">Cancel</Link>
        </Button>
      </div>
      <div className="mt-6">
        <PurchaseRequestForm
          defaultRequestType="sponsorship_form"
          successRedirectUrl="/procurement-management/sponsorship-forms"
        />
      </div>
    </Container>
  );
}
