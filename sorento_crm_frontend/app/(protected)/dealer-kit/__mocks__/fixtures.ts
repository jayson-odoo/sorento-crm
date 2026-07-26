/**
 * Test-only fixtures.
 *
 * The Phase 1 prototype fixtures are gone - the UI is wired to the real API now.
 * What survives here is the small amount of sample data the component tests
 * need, kept because deleting it would mean each test hand-rolling its own
 * near-identical page rows.
 */

import type { PageSummary } from '@/lib/dealer-kit/types';

export const MOCK_PAGES: PageSummary[] = [
  {
    id: 'page-2026-bathroom',
    name: 'Bathroom Catalogue 2026',
    slug: '2026-bathroom',
    updatedAt: '2026-07-24T09:12:00',
    publishedVersion: 2,
    latestVersion: 3,
    publicPath: '/c/SRT/2026-bathroom',
  },
  {
    id: 'page-kitchen-2026',
    name: 'Kitchen Sinks 2026',
    slug: '2026-kitchen',
    updatedAt: '2026-07-11T14:02:00',
    publishedVersion: null,
    latestVersion: 1,
    publicPath: '/c/SRT/2026-kitchen',
  },
];
