import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { BrochureImagePicker } from './components/BrochureImagePicker';

export const metadata: Metadata = {
  title: 'Brochure Images',
  description: 'Choose which photo of each product a catalogue tile shows.',
};

export default function DealerKitBrochureImagesPage() {
  return (
    <Container width="fluid">
      <PageHeader
        title="Brochure Images"
      >
        {/* Where the chosen image ends up. Said here because the buyer sent from the
            reorder plan's empty photo state arrives on this page with no other clue that
            the two screens are the same setting. */}
        <p className="text-sm text-muted-foreground">
          The image chosen here is the product&apos;s primary photo everywhere in the CRM.
        </p>
        
      </PageHeader>

      <BrochureImagePicker />
    </Container>
  );
}
