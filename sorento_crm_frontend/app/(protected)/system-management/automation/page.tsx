import type { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import AutomationsList from './components/AutomationsList';

export const metadata: Metadata = {
  title: 'Automation',
  description: 'Configurable rules that send templated emails on schedules.',
};

export default function AutomationPage() {
  return (
    <>
      <Container>
        <PageHeader title="Automation" />
      </Container>
      <Container>
        <AutomationsList />
      </Container>
    </>
  );
}
