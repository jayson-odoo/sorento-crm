import { Metadata } from 'next';
import { MyCustomerAsksClient } from './components/MyCustomerAsksClient';

export const metadata: Metadata = {
  title: 'Customer asks',
  description: 'What your customers asked on WhatsApp, to clear one by one.',
};

export default function CustomerAsksPage() {
  return <MyCustomerAsksClient />;
}
