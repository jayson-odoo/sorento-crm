'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { KindsTab } from './KindsTab';
import { PoliciesTab } from './PoliciesTab';
import { RulesTab } from './RulesTab';

/**
 * One area, three tabs, NOT three sidebar entries. AC-P7's zero-rule flag is the
 * point of the slice, and a Kind list buried behind its own menu entry is how it
 * stays invisible - the admin fixing a policy has to be standing next to the
 * count that says the policy can never be reached.
 */
export function WarrantyConfigView() {
  return (
    <Tabs defaultValue="policies" className="w-full">
      <TabsList variant="line" className="mb-5 w-full justify-start overflow-x-auto">
        <TabsTrigger value="policies">Policies</TabsTrigger>
        <TabsTrigger value="kinds">Kinds</TabsTrigger>
        <TabsTrigger value="rules">Rules</TabsTrigger>
      </TabsList>

      <TabsContent value="policies" className="mt-0 focus-visible:outline-none">
        <PoliciesTab />
      </TabsContent>
      <TabsContent value="kinds" className="mt-0 focus-visible:outline-none">
        <KindsTab />
      </TabsContent>
      <TabsContent value="rules" className="mt-0 focus-visible:outline-none">
        <RulesTab />
      </TabsContent>
    </Tabs>
  );
}
