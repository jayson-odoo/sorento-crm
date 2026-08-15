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
          {/* Where the chosen image ends up. Said here because the buyer sent from the
              reorder plan's empty photo state arrives on this page with no other clue that
              the two screens are the same setting. */}
          <p className="text-sm text-muted-foreground">
            The image chosen here is the product&apos;s primary photo everywhere in the CRM.
          </p>
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
