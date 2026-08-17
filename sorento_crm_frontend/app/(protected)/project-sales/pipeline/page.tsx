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
import { PipelineClient } from './components/PipelineClient';

export const metadata: Metadata = {
  title: 'Project Pipeline',
  description: 'Registered project pursuits, their stage, and who owns each one.',
};

export default function ProjectPipelinePage() {
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
              <BreadcrumbPage>Pipeline</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <PipelineClient />
      </Container>
    </RequireAccess>
  );
}
