import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import FormSLAConfigList from './components/FormSLAConfigList';

export const metadata: Metadata = {
  title: 'Form SLA Configuration',
  description:
    'Configure per-form SLA stages: which transitions start, mark responded, mark resolved.',
};

export default function FormSLAConfigPage() {
  return (
    <Container>
      <PageHeader title="Form SLA Configuration" />
      <div className="mt-6">
        <FormSLAConfigList />
      </div>
    </Container>
  );
}
