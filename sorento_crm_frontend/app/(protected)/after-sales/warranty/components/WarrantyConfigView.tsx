'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useUrlTab } from '@/hooks/useUrlTab';
import { KindsTab } from './KindsTab';
import { PoliciesTab } from './PoliciesTab';
import { RulesTab } from './RulesTab';

const TABS = ['policies', 'kinds', 'rules'] as const;

export default function WarrantyConfigView() {
  const [tab, setTab] = useUrlTab({ tabs: TABS, defaultTab: 'policies' });
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList variant="line" className="mb-5">
        <TabsTrigger value="policies">Policies</TabsTrigger>
        <TabsTrigger value="kinds">Kinds</TabsTrigger>
        <TabsTrigger value="rules">Rules</TabsTrigger>
      </TabsList>
      <TabsContent value="policies">{tab === 'policies' && <PoliciesTab />}</TabsContent>
      <TabsContent value="kinds">{tab === 'kinds' && <KindsTab />}</TabsContent>
      <TabsContent value="rules">{tab === 'rules' && <RulesTab />}</TabsContent>
    </Tabs>
  );
}
