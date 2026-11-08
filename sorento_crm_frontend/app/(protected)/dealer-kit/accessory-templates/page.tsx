import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { AccessoryTemplatesList } from './components/AccessoryTemplatesList';

export const metadata: Metadata = {
  title: 'Accessory Templates',
  description: 'Manage saved accessories box designs used in tag templates.',
};

export default function AccessoryTemplatesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Accessory Templates" />
      </Container>

      <Container>
        <AccessoryTemplatesList />
      </Container>
    </>
  );
}
