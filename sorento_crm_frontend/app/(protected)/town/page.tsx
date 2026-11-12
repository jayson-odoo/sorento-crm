import { Metadata } from 'next';
import { TownPage } from './components/TownPage';

export const metadata: Metadata = {
  title: 'Town',
  description: 'Today at a glance: sales, dealers, low stock, deliveries and approvals.',
};

export default function Page() {
  return <TownPage />;
}
