'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from '@/components/ui/context-menu';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import DetailActions from '@/components/common/DetailActions';
import AuditTrail from '@/components/audit/AuditTrail';
import { useUrlTab } from '@/hooks/useUrlTab';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useEffectiveIsSuperadmin } from '@/hooks/useEffectiveIsSuperadmin';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import { useDefectOptions, useKindOptions, usePolicy, usePolicyTerms } from '../hooks/useWarrantyConfig';
import { POLICY_LIFECYCLE_LABEL, formatCivilDate, policyLifecycle } from '../lib/warrantyLabels';
import { getPolicies } from '../services/warrantyConfigService';
import type { WarrantyTerm } from '../types/warranty.types';
import { SupersedeDialog } from './SupersedeDialog';
import { TermFormDialog } from './TermFormDialog';

const TABS = ['details', 'terms', 'history'] as const;
const LIFECYCLE_VARIANT = { in_force: 'success', scheduled: 'info', superseded: 'secondary' } as const;

const pagerQuery = {
  listQueryKey: (p: ListPagerParams) => ['warranty-policies', p.pageIndex, p.pageSize, p.sorting, p.searchQuery],
  fetchPage: (p: ListPagerParams): Promise<ListPagerPage> =>
    getPolicies({ pageIndex: p.pageIndex, pageSize: p.pageSize, sorting: p.sorting, searchQuery: p.searchQuery }),
};

function cover(term: WarrantyTerm): string {
  if (term.is_lifetime) return 'Lifetime';
  const months = term.duration_months ?? 0;
  if (months > 0 && months % 12 === 0) {
    const years = months / 12;
    return `${years} year${years === 1 ? '' : 's'}`;
  }
  return `${months} month${months === 1 ? '' : 's'}`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

const HEADS = ['Part', 'Cover', 'Defects', 'Installation'];

export default function PolicyDetail({ policyId }: { policyId: string }) {
  const { data: policy, isLoading } = usePolicy(policyId);
  const { data: terms, isLoading: termsLoading } = usePolicyTerms(policyId);
  const { data: kinds = [] } = useKindOptions();
  const { data: defects = [] } = useDefectOptions();
  const [superseding, setSuperseding] = useState(false);
  const isAdmin = useEffectiveIsSuperadmin() === true;
  const [termForm, setTermForm] = useState<{ open: boolean; term: WarrantyTerm | null }>({ open: false, term: null });
  const [menuTerm, setMenuTerm] = useState<WarrantyTerm | null>(null);
  const removeTerm = useDeferredRowAction({
    actionKey: 'warranty_term.delete',
    entityType: 'warranty_term',
    verb: 'Deleting',
    successMessage: 'Term deleted.',
    invalidateKeys: [['warranty-terms'], ['warranty-policies'], ['warranty-policy'], ['warranty-kinds']],
  });
  const [tab, setTab] = useUrlTab({ tabs: TABS, defaultTab: 'terms' });

  if (isLoading || !policy) {
    return isLoading ? (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    ) : (
      <p className="py-12 text-center text-muted-foreground">Policy not found</p>
    );
  }

  const state = policyLifecycle(policy);
  const kindName = (id: string) => kinds.find((k) => k.id === id)?.name ?? '-';
  const defectNames = (term: WarrantyTerm) =>
    term.covered_defect_type_ids?.length
      ? term.covered_defect_type_ids.map((id) => defects.find((d) => d.id === id)?.label ?? '-').join(', ')
      : 'All defects';
  const groups = new Map<string, WarrantyTerm[]>();
  for (const term of terms ?? []) groups.set(term.kind_id, [...(groups.get(term.kind_id) ?? []), term]);
  const ordered = [...groups.entries()].sort((a, b) => kindName(a[0]).localeCompare(kindName(b[0])));

  const termGroups = (
    <>
        {termsLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : ordered.length === 0 ? (
          <Card>
            <CardContent className="py-6 text-center">
              <h3 className="text-sm font-medium">No terms</h3>
              <p className="mt-1 text-sm text-muted-foreground">This policy gives no cover to any kind yet.</p>
            </CardContent>
          </Card>
        ) : (
          ordered.map(([kindId, rows]) => (
            <Card key={kindId}>
              <CardHeader>
                <CardTitle>{kindName(kindId)}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[34rem] table-fixed text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        {HEADS.map((h) => (
                          <th key={h} className="px-2 py-2 font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[...rows]
                        .sort((a, b) => a.part_name.localeCompare(b.part_name))
                        .map((t) => (
                          // eslint-disable-next-line jsx-a11y/control-has-associated-label -- a table row, named by its cells
                            <tr key={t.id} data-term-id={t.id} className="border-b last:border-0">
                            <td className="px-2 py-2"><span className="block truncate" title={t.part_name}>{t.part_name}</span></td>
                            <td className="px-2 py-2"><span className="block truncate">{cover(t)}</span></td>
                            <td className="px-2 py-2"><span className="block truncate" title={defectNames(t)}>{defectNames(t)}</span></td>
                            <td className="px-2 py-2"><span className="block truncate">{t.installation_included ? 'Included' : 'Excluded'}</span></td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ))
        )}
    </>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="text-2xl font-bold break-words">{policy.version}</h2>
          <Badge variant={LIFECYCLE_VARIANT[state]} size="sm" className="shrink-0">
            {POLICY_LIFECYCLE_LABEL[state]}
          </Badge>
        </div>
        <DetailActions
          pager={{ ...pagerQuery, detailPath: '/after-sales/warranty/policies', currentId: policyId, ariaLabel: 'policy' }}
          primary={state === 'in_force' ? <Button onClick={() => setSuperseding(true)}>Supersede</Button> : undefined}
          dialogs={
            superseding ? <SupersedeDialog open onOpenChange={(open) => !open && setSuperseding(false)} policy={policy} /> : undefined
          }
        />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList variant="line" className="mb-5">
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="terms">Terms{terms ? ` ${terms.length}` : ''}</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>
        <TabsContent value="details">
          <Card>
            <CardHeader>
              <CardTitle>Policy</CardTitle>
            </CardHeader>
            <CardContent>
              <dl>
                <Field label="In force from">{formatCivilDate(policy.effective_from)}</Field>
                <Field label="In force to">{policy.effective_to ? formatCivilDate(policy.effective_to) : '-'}</Field>
                <Field label="Policy text">
                  <span className="whitespace-pre-wrap">{policy.policy_text?.trim() || '-'}</span>
                </Field>
              </dl>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="terms" className="space-y-6">
          {isAdmin && (
            <div className="flex justify-end">
              <Button onClick={() => setTermForm({ open: true, term: null })}>
                <Plus />
                Create
              </Button>
            </div>
          )}
          {isAdmin ? (
            <ContextMenu modal={false}>
              <ContextMenuTrigger asChild>
                <div
                  className="space-y-6"
                  // A right-click outside a term row stops here, so the browser's own menu shows.
                  onContextMenuCapture={(event) => {
                    const el = (event.target as Element).closest('[data-term-id]');
                    const found = (terms ?? []).find((t) => t.id === el?.getAttribute('data-term-id'));
                    if (!found) {
                      event.stopPropagation();
                      return;
                    }
                    setMenuTerm(found);
                  }}
                >
                  {termGroups}
                </div>
              </ContextMenuTrigger>
              <ContextMenuContent className="w-48">
                {menuTerm && (
                  <>
                    <ContextMenuItem onSelect={() => setTermForm({ open: true, term: menuTerm })}>Edit</ContextMenuItem>
                    <ContextMenuItem
                      onSelect={() =>
                        removeTerm.run({ id: menuTerm.id, subject: `${kindName(menuTerm.kind_id)}: ${menuTerm.part_name}` })
                      }
                    >
                      Delete
                    </ContextMenuItem>
                  </>
                )}
              </ContextMenuContent>
            </ContextMenu>
          ) : (
            <div className="space-y-6">
              {termGroups}
            </div>
          )}
          {termForm.open && (
            <TermFormDialog
              open
              onOpenChange={(open) => !open && setTermForm({ open: false, term: null })}
              policyId={policyId}
              term={termForm.term}
            />
          )}
        </TabsContent>
        <TabsContent value="history">
          <AuditTrail entityType="warranty_policies" entityId={policyId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
