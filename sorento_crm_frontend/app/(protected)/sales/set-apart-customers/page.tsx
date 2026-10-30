import { Metadata } from 'next';
import SetApartView from './components/SetApartView';

export const metadata: Metadata = {
  title: 'Set-apart customers',
  description: 'Customers reported apart from Dealer and Project team sales.',
};

export default function SetApartCustomersPage() {
  return <SetApartView />;
}
