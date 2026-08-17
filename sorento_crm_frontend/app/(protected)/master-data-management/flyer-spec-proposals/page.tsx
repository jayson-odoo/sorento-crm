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

import { FlyerSpecBatchesList } from './components/FlyerSpecBatchesList';

export const metadata: Metadata = {
  title: 'Flyer Spec Proposals',
  description:
    'What each flyer says about the product master, ready to review.',
};

export default function FlyerSpecProposalsPage() {
  return (
    <Container width="fluid">
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Flyer Spec Proposals</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Master Data</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Flyer Spec Proposals</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
      </Toolbar>

      <FlyerSpecBatchesList />
    </Container>
  );
}
