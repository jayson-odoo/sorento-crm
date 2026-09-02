'use client';

import { CatalogueFreshnessLine } from './CatalogueFreshnessLine';
import { SpecRegistryGrid } from './SpecRegistryGrid';

/** The registry list body: freshness line above the grid (AC-A.2, AC-A.3). */
export function SpecRegistryPage() {
  return (
    <div className="flex flex-col gap-3">
      <CatalogueFreshnessLine />
      <SpecRegistryGrid />
    </div>
  );
}

export default SpecRegistryPage;
