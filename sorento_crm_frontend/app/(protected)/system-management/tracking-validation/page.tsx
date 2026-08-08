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
import RequireAccess from '@/app/components/common/RequireAccess';
import TrackingValidationList from './components/TrackingValidationList';

export const metadata: Metadata = {
  title: 'Tracking Validation',
  description:
    'Compare liner and CIDB feed observations against the dates entered by hand.',
};

export default function TrackingValidationPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Tracking Validation</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>System Management</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions></ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <TrackingValidationList />
      </Container>
    </RequireAccess>
  );
}
