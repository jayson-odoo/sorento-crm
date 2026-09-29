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
      <PageHeader title="Brochure Images" />

      <BrochureImagePicker />
    </Container>
  );
}
