'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useUrlTab } from '@/hooks/useUrlTab';
import { KindsTab } from './KindsTab';
import { PoliciesTab } from './PoliciesTab';
import { RulesTab } from './RulesTab';

const TABS = ['policies', 'kinds', 'rules'] as const;
// The list state each tab writes to the address: it belongs to that tab and is dropped on a switch.
const LIST_PARAMS = ['page', 'limit', 'sort', 'dir', 'query', 'is_active', 'has_no_rule', 'kind_id'];

export default function WarrantyConfigView() {
  const [tab, setTab] = useUrlTab({ tabs: TABS, defaultTab: 'policies' });
  const switchTab = (next: string) => {
    const params = new URLSearchParams(window.location.search);
    for (const key of LIST_PARAMS) params.delete(key);
    const search = params.toString();
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${search ? `?${search}` : ''}`);
    setTab(next);
  };
  return (
    <Tabs value={tab} onValueChange={switchTab}>
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
