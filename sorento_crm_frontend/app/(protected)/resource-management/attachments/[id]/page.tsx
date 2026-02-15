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
import AttachmentDetail from '../components/AttachmentDetail';

export const metadata: Metadata = {
  title: 'Attachment Details',
  description: 'View attachment details and actions.',
};

export default async function AttachmentDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ from?: string; directoryId?: string }>;
}) {
  const resolvedSearchParams = await searchParams;
  const fromDirectories = resolvedSearchParams?.from === 'directories';
  const directoryId = resolvedSearchParams?.directoryId;

  const backUrl = fromDirectories
    ? `/resource-management/attachment-directories${directoryId ? `?directoryId=${directoryId}` : ''}`
    : '/resource-management/attachments';

  return (
    <Container>
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/">Home</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href={backUrl}>
              {fromDirectories ? 'Attachment Directories' : 'Attachments'}
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Details</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="mt-6">
        <AttachmentDetailWrapper params={params} fromDirectories={fromDirectories} directoryId={directoryId} />
      </div>
    </Container>
  );
}

async function AttachmentDetailWrapper({
  params,
  fromDirectories,
  directoryId,
}: {
  params: Promise<{ id: string }>;
  fromDirectories: boolean;
  directoryId?: string;
}) {
  const { id } = await params;
  return <AttachmentDetail attachmentId={id} fromDirectories={fromDirectories} directoryId={directoryId} />;
}
