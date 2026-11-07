import { Suspense } from 'react';
import { Metadata } from 'next';
import LeaderboardView from './components/LeaderboardView';

export const metadata: Metadata = {
  title: 'Sales leaderboard',
  description: 'Sales ranked by sales person, customer, product, brand, category and channel.',
};

export default function SalesLeaderboardPage() {
  return (
    <Suspense fallback={null}>
      <LeaderboardView />
    </Suspense>
  );
}
