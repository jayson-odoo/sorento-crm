import { Metadata } from 'next';
import SalesTeamsView from './components/SalesTeamsView';

export const metadata: Metadata = {
  title: 'Sales Teams',
  description: 'Sales teams and the agents in each.',
};

export default function SalesTeamsPage() {
  return <SalesTeamsView />;
}
