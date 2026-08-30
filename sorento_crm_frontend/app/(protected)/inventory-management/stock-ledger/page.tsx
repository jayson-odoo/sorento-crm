import StockLedgerList from './components/StockLedgerList';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

export default function StockLedgerPage() {
  return (
    <>
      <Container>
        <PageHeader title="Stock Ledger" />
      </Container>

      <Container>
        <StockLedgerList />
      </Container>
    </>
  );
}
