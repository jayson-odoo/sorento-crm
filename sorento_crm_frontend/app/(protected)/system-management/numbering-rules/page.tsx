import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import NumberingRulesList from './components/NumberingRulesList';

export const metadata: Metadata = {
  title: 'Running Numbers',
  description: 'Configure document numbering rules for purchase requests and sponsorship forms.',
};

export default function NumberingRulesPage() {
  return (
    <RequireAccess permission="system.numbering_rules.view">
      <Container>
        <PageHeader title="Running Numbers" />
      </Container>

      <Container className="space-y-6">
        <NumberingRulesList />
      </Container>
    </RequireAccess>
  );
}
