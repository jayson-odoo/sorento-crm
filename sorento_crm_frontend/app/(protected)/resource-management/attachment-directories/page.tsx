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
  title: 'Attachment Directories',
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
            <ToolbarTitle>Attachment Directories</ToolbarTitle>
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
                  <BreadcrumbPage>Attachment Directories</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>

      <Container className="flex flex-col flex-1 min-h-0">
        <AttachmentDirectoriesView initialDirectoryId={initialDirectoryId} />
      </Container>
    </>
  );
}
