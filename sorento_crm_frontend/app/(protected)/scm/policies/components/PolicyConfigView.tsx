'use client';

import {
  Coins,
  Container,
  Eye,
  Layers,
  Repeat,
  SlidersHorizontal,
  Star,
  Truck,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ContainerSizesPanel } from './ContainerSizesPanel';
import { CurrencyRatesPanel } from './CurrencyRatesPanel';
import { ClassificationThresholdsPanel } from './ClassificationThresholdsPanel';
import { FulfilmentPriorityPanel } from './FulfilmentPriorityPanel';
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
      <TabsList className="mb-5">
        <TabsTrigger value="planning-mode">
          <SlidersHorizontal />
          <span>Planning mode</span>
        </TabsTrigger>
        <TabsTrigger value="reorder">
          <Repeat />
          <span>Reorder policies</span>
        </TabsTrigger>
        <TabsTrigger value="fulfilment">
          <Truck />
          <span>Fulfilment</span>
        </TabsTrigger>
        <TabsTrigger value="classification">
          <Layers />
          <span>Classification thresholds</span>
        </TabsTrigger>
        <TabsTrigger value="supplier">
          <Star />
          <span>Supplier scoring</span>
        </TabsTrigger>
        <TabsTrigger value="containers">
          <Container />
          <span>Container sizes</span>
        </TabsTrigger>
        <TabsTrigger value="currency">
          <Coins />
          <span>Exchange rates</span>
        </TabsTrigger>
        <TabsTrigger value="preview">
          <Eye />
          <span>Resolution preview</span>
        </TabsTrigger>
      </TabsList>

      <TabsContent value="planning-mode" className="mt-0 max-w-3xl focus-visible:outline-none">
        <PlanningModePanel />
      </TabsContent>

      <TabsContent value="reorder" className="mt-0 focus-visible:outline-none">
        <ReorderPolicyGrid />
      </TabsContent>

      <TabsContent value="fulfilment" className="mt-0 max-w-3xl focus-visible:outline-none">
        <FulfilmentPriorityPanel />
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
