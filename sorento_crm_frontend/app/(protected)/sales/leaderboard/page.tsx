import { Metadata } from 'next';
import LeaderboardView from './components/LeaderboardView';

export const metadata: Metadata = {
  title: 'Sales leaderboard',
  description: 'Invoiced sales ranked by sales person.',
};

export default function SalesLeaderboardPage() {
  return <LeaderboardView />;
}
