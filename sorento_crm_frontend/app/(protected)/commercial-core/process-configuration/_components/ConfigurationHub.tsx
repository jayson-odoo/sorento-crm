'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { cn } from '@/lib/utils';
import { ConfigurationStagesTab } from './tabs/ConfigurationStagesTab';
import { ConfigurationProjectTasksTab } from './tabs/ConfigurationProjectTasksTab';
import { ConfigurationQuotationsTab } from './tabs/ConfigurationQuotationsTab';
import { ConfigurationReferenceDataTab } from './tabs/ConfigurationReferenceDataTab';
import type { ReferenceSubTab } from './tabs/ConfigurationReferenceDataTab';

const MAIN_ORDER = ['stages', 'project-tasks', 'quotations', 'reference'] as const;
type MainTab = (typeof MAIN_ORDER)[number];

const MAIN_LABEL: Record<MainTab, string> = {
  stages: 'Stages',
  'project-tasks': 'Task Templates',
  quotations: 'Quotations',
  reference: 'Reference Data',
};

function parseMainTab(v: string | null): MainTab {
  if (v === 'project-tasks' || v === 'quotations' || v === 'reference' || v === 'stages') return v;
  return 'stages';
}

function parseRef(v: string | null): ReferenceSubTab {
  const ok = ['countries', 'states', 'budget', 'closure', 'property', 'sources', 'contact'];
  if (v && ok.includes(v)) return v as ReferenceSubTab;
  return 'countries';
}

export function ConfigurationHub() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = parseMainTab(searchParams.get('tab'));
  const refSub = parseRef(searchParams.get('ref'));

  const setTab = (next: MainTab) => {
    const qs = new URLSearchParams(searchParams.toString());
    qs.set('tab', next);
    if (next === 'reference') {
      if (!qs.get('ref')) qs.set('ref', 'countries');
    } else {
      qs.delete('ref');
    }
    router.replace(`/commercial-core/process-configuration?${qs.toString()}`, { scroll: false });
  };

  return (
    <>
        <header className="mb-10 space-y-2">
          <h1 className="text-2xl font-medium tracking-tight text-[#0a0a0a]">Configuration</h1>
        </header>

        <div className="mb-6 overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white">
          <div className="grid grid-cols-2 border-b border-[#e5e7eb] md:grid-cols-4">
            {MAIN_ORDER.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={cn(
                  'border-b-2 py-3 text-center text-sm font-medium transition-colors',
                  tab === id ? 'border-[#e7000b] text-[#e7000b]' : 'border-transparent text-[#4a5565] hover:text-foreground',
                )}
              >
                {MAIN_LABEL[id]}
              </button>
            ))}
          </div>
        </div>

        {tab === 'stages' ? <ConfigurationStagesTab /> : null}
        {tab === 'project-tasks' ? <ConfigurationProjectTasksTab /> : null}
        {tab === 'quotations' ? <ConfigurationQuotationsTab /> : null}
        {tab === 'reference' ? <ConfigurationReferenceDataTab sub={refSub} /> : null}
    </>
  );
}
