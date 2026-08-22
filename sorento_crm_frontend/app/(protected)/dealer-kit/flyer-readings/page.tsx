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
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';

import { FlyerReadingsList } from './components/FlyerReadingsList';

export const metadata: Metadata = {
  title: 'Flyers',
  description: 'Turn a printed flyer into a draft brochure.',
};

export default function DealerKitFlyerReadingsPage() {
  return (
    <Container width="fluid">
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Flyers</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Dealer Kit</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Flyers</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
      </Toolbar>

      <FlyerReadingsList />
    </Container>
  );
}
