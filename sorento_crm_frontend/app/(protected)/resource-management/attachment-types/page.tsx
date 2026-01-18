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
import AttachmentTypesList from './components/AttachmentTypesList';

export const metadata: Metadata = {
  title: 'Attachment Types',
  description: 'Manage attachment types.',
};

export default async function AttachmentTypesPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Attachment Types</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Resource Management</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>

      <Container>
        <AttachmentTypesList />
      </Container>
    </>
  );
}
