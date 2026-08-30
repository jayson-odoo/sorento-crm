import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { MarketSignalsView } from '../market/components/MarketSignalsView';

export const metadata: Metadata = {
  title: 'Market Signals',
  description: 'Market and economic advisory signals and research topic configuration.',
};

export default function ScmMarketSignalsPage() {
  return (
    <>
      <Container width="fluid">
        <PageHeader title="Market Signals" />
      </Container>

      <Container width="fluid">
        <MarketSignalsView />
      </Container>
    </>
  );
}
