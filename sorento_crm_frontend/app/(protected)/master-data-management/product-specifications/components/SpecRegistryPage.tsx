'use client';

import { SpecRegistryGrid } from './SpecRegistryGrid';

/**
 * The registry list body (AC-S3.4): just the grid. No status pill, no Re-read
 * button, no "Never read" line, no "Rules changed since" badge - a rule saved
 * re-reads exactly the products it changes by itself (D10), so the list only
 * ever needs to show current values (owner ruling, 27 Sep 2026).
 */
export function SpecRegistryPage() {
  return (
    <div className="flex flex-col gap-3">
      <SpecRegistryGrid />
    </div>
  );
}

export default SpecRegistryPage;
