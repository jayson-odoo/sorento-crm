import { Metadata } from 'next';
import DealerAccessView from './components/DealerAccessView';

export const metadata: Metadata = {
  title: 'Dealer access',
  description: 'The people who can use your dealer accounts.',
};

export default function DealerAccessPage() {
  return <DealerAccessView />;
}
