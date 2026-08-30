import type { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import EmailTemplatesList from './components/EmailTemplatesList';

export const metadata: Metadata = {
  title: 'Email Templates',
  description: 'Author reusable email templates with Jinja2 placeholders.',
};

export default function EmailTemplatesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Email Templates" />
      </Container>
      <Container>
        <EmailTemplatesList />
      </Container>
    </>
  );
}
