'use client';

import { SearchRankingSettings } from './components/SearchRankingSettings';

/**
 * Settings -> Search ranking (AC-C.1). Reads the spec-registry ranking policy
 * directly rather than through `SettingsProvider` - this is not a
 * `system_settings` column, it is its own API.
 */
export default function SearchRankingSettingsPage() {
  return <SearchRankingSettings />;
}
