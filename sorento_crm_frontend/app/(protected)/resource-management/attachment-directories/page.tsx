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
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import AttachmentDirectoriesView from './components/AttachmentDirectoriesView';

export const metadata: Metadata = {
  title: 'Files',
  description: 'Manage folders and attachments.',
};

export default async function AttachmentDirectoriesPage({
  searchParams,
}: {
  searchParams: Promise<{ directoryId?: string }>;
}) {
  const resolvedSearchParams = await searchParams;
  const initialDirectoryId = resolvedSearchParams?.directoryId || null;

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Files</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/resource-management/attachments">Resource Management</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Files</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>

      <Container className="flex flex-col h-[calc(100vh-12rem)] min-h-[480px] overflow-hidden">
        <AttachmentDirectoriesView initialDirectoryId={initialDirectoryId} />
      </Container>
    </>
  );
}
