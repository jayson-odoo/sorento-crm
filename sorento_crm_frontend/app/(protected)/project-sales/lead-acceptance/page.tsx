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
import RequireAccess from '@/app/components/common/RequireAccess';
import { AwaitingAcceptanceClient } from './components/AwaitingAcceptanceClient';

export const metadata: Metadata = {
  title: 'Awaiting Acceptance',
  description: 'Leads assigned to a salesperson who has not accepted them yet.',
};

export default function LeadAcceptancePage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/">Home</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Project Sales</BreadcrumbPage>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Awaiting Acceptance</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <AwaitingAcceptanceClient />
      </Container>
    </RequireAccess>
  );
}
