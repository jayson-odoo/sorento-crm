'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ContainerSizesPanel } from './ContainerSizesPanel';
import { CurrencyRatesPanel } from './CurrencyRatesPanel';
import { ClassificationThresholdsPanel } from './ClassificationThresholdsPanel';
import { PlanningModePanel } from './PlanningModePanel';
import { ReorderPolicyGrid } from './ReorderPolicyGrid';
import { ResolutionPreviewCard } from './ResolutionPreviewCard';
import { SupplierScoringPanel } from './SupplierScoringPanel';

/**
 * The SCM Policies area - one screen tuning the three reorder-engine policy
 * families plus a resolution preview. Every tab renders its own section with
 * explicit loading / empty / error states (per CRUD UX standard).
 */
export function PolicyConfigView() {
  return (
    <Tabs defaultValue="planning-mode" className="w-full">
      <TabsList variant="line" className="mb-5 w-full justify-start overflow-x-auto">
        <TabsTrigger value="planning-mode">Planning mode</TabsTrigger>
        <TabsTrigger value="reorder">Reorder policies</TabsTrigger>
        <TabsTrigger value="classification">Classification thresholds</TabsTrigger>
        <TabsTrigger value="supplier">Supplier scoring</TabsTrigger>
        <TabsTrigger value="containers">Container sizes</TabsTrigger>
        <TabsTrigger value="currency">Exchange rates</TabsTrigger>
        <TabsTrigger value="preview">Resolution preview</TabsTrigger>
      </TabsList>

      <TabsContent value="planning-mode" className="mt-0 max-w-3xl focus-visible:outline-none">
        <PlanningModePanel />
      </TabsContent>

      <TabsContent value="reorder" className="mt-0 focus-visible:outline-none">
        <ReorderPolicyGrid />
      </TabsContent>

      <TabsContent value="classification" className="mt-0 max-w-3xl focus-visible:outline-none">
        <ClassificationThresholdsPanel />
      </TabsContent>

      <TabsContent value="supplier" className="mt-0 max-w-3xl focus-visible:outline-none">
        <SupplierScoringPanel />
      </TabsContent>

      <TabsContent value="containers" className="mt-0 max-w-3xl focus-visible:outline-none">
        <ContainerSizesPanel />
      </TabsContent>

      <TabsContent value="currency" className="mt-0 max-w-3xl focus-visible:outline-none">
        <CurrencyRatesPanel />
      </TabsContent>

      <TabsContent value="preview" className="mt-0 max-w-4xl focus-visible:outline-none">
        <ResolutionPreviewCard />
      </TabsContent>
    </Tabs>
  );
}
