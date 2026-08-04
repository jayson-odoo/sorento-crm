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
import { QuotationDocumentPrototype } from '../_prototype/QuotationDocumentPrototype';

export const metadata: Metadata = {
  title: 'Quotation document (preview)',
  description: 'Phase 1 prototype of the multi-scope quotation document.',
};

/**
 * PHASE 1 ONLY. This route and everything under `_prototype/` are deleted when the real
 * document screen lands in Phase 2 - it exists so the shape can be argued about in a browser
 * before a table is created, which is cheaper than arguing about it after.
 *
 * Reachable from the Quotations tab so it is reviewed the way it will be used: by clicking,
 * not by pasting a URL.
 */
export default async function QuotationDocumentPreviewPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6 pb-64">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/">Home</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href="/project-sales/pipeline">Project Sales</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href={`/project-sales/${projectId}?tab=quotations`}>
                Quotations
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Document preview</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <QuotationDocumentPrototype projectId={projectId} />
      </Container>
    </RequireAccess>
  );
}
