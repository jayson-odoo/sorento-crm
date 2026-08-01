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

import { BrochureImagePicker } from './components/BrochureImagePicker';

export const metadata: Metadata = {
  title: 'Brochure Images',
  description: 'Choose which photo of each product a catalogue tile shows.',
};

export default function DealerKitBrochureImagesPage() {
  return (
    <Container width="fluid">
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Brochure Images</ToolbarTitle>
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
                <BreadcrumbPage>Brochure Images</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
      </Toolbar>

      <BrochureImagePicker />
    </Container>
  );
}
