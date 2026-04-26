import { Suspense } from 'react';
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
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { Skeleton } from '@/components/ui/skeleton';
import LeadsList from './components/LeadsList';

export const metadata: Metadata = {
  title: 'Leads',
  description: 'Commercial leads.',
};

export default function CommercialLeadsPage() {
  return (
    <>
      <Container width="fluid">
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Leads</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Commercial</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
      </Container>

      <Container width="fluid" className="bg-[#f9fafb] py-6">
        <Suspense fallback={<Skeleton className="h-[480px] w-full" />}>
          <LeadsList />
        </Suspense>
      </Container>
    </>
  );
}
