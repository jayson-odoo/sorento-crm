import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { StockClaimsClient } from './components/StockClaimsClient';

export const metadata: Metadata = {
  title: 'Stock Claims',
  description: 'Cross-project stock requests waiting on an answer, and the ones you raised.',
};

export default function ProjectStockClaimsPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <StockClaimsClient />
      </Container>
    </RequireAccess>
  );
}
