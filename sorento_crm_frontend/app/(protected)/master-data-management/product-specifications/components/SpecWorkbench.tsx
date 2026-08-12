'use client';

import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import FindabilityPanel from './FindabilityPanel';
import { getSpecRegistry } from '../services/productSpecService';
import ProductSpecsList from './ProductSpecsList';
import SearchTuning from './SearchTuning';
import SpecRegistryTable from './SpecRegistryTable';
import SpecSearchPreview from './SpecSearchPreview';

/**
 * Three jobs, in the order people do them: ask, tune, check.
 *
 * The page used to be one column of five cards with no stated relationship, so the
 * only way to find the thing you wanted was to read all of it. The jobs are genuinely
 * different — trying a phrase is a question, editing a spec is a change, reading the
 * derived data is verification — and each one wants the whole width when you are doing it.
 *
 * The phrase box stays OUTSIDE the tabs on purpose. It is the only part of this screen
 * that tells you whether a change worked, so it has to still be there after you make one.
 */
export default function SpecWorkbench() {
  const [specCount, setSpecCount] = useState<number | null>(null);

  useEffect(() => {
    getSpecRegistry()
      .then((r) => setSpecCount(r.keys.length))
      .catch(() => setSpecCount(null));
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <SpecSearchPreview />

      <Tabs defaultValue="specs" className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start overflow-x-auto">
          <TabsTrigger value="specs" className="gap-2">
            Specifications
            {specCount !== null && (
              <Badge variant="secondary" size="sm" appearance="light" shape="circle">
                {specCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="ranking">Ranking</TabsTrigger>
          <TabsTrigger value="catalogue">Catalogue</TabsTrigger>
          <TabsTrigger value="findability">Flyer check</TabsTrigger>
        </TabsList>

        <TabsContent value="specs" className="mt-0 focus-visible:outline-none">
          <SpecRegistryTable />
        </TabsContent>

        <TabsContent value="ranking" className="mt-0 focus-visible:outline-none">
          <SearchTuning />
        </TabsContent>

        <TabsContent value="findability" className="mt-0 focus-visible:outline-none">
          <FindabilityPanel />
        </TabsContent>

        <TabsContent value="catalogue" className="mt-0 focus-visible:outline-none">
          <ProductSpecsList />
        </TabsContent>
      </Tabs>
    </div>
  );
}

