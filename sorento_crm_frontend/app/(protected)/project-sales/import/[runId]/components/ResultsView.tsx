'use client';

import * as React from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import AuditTrail from '@/components/audit/AuditTrail';
import { OutcomeBreakdownCard } from '@/app/(protected)/system-management/import-jobs/components/OutcomeBreakdownCard';
import type { ImportJobResultEnvelope } from '@/app/(protected)/system-management/import-jobs/types/importJob.types';
import type { ProjectImportRun } from '../../../_shared/types/projectImport.types';
import { OutcomeTiles, ReportRowsGrid } from './ReportRows';
import { ValuesStep } from './ValuesStep';

/**
 * Results (AC-PI-48): tabs Results | Values | History. The breakdown is the shared import
 * card over the run's own outcome envelope; the rows are the run's report rows.
 */
export function ResultsView({ run }: { run: ProjectImportRun }) {
  const [tab, setTab] = React.useState('results');
  const counts = run.result_counts ?? run.preview_counts;

  return (
    <Tabs value={tab} onValueChange={setTab} className="space-y-4">
      <TabsList variant="line" className="w-full justify-start overflow-x-auto">
        <TabsTrigger value="results">Results</TabsTrigger>
        <TabsTrigger value="values">Values</TabsTrigger>
        <TabsTrigger value="history">History</TabsTrigger>
      </TabsList>
      <TabsContent value="results" className="space-y-4">
        {run.status === 'importing' ? (
          <p className="text-sm text-muted-foreground">Importing…</p>
        ) : (
          <>
            <OutcomeTiles counts={counts} done={run.status !== 'previewed'} />
            {run.revert_result && run.revert_result.kept.length > 0 && (
              <div className="rounded-lg border p-3 text-sm">
                <p className="font-medium">Kept, changed since the import</p>
                <ul className="mt-1 list-disc ps-5 text-muted-foreground">
                  {run.revert_result.kept.map((k) => (
                    <li key={`${k.entity_type}-${k.label}`}>{k.label}</li>
                  ))}
                </ul>
              </div>
            )}
            <OutcomeBreakdownCard
              result={(run.result ?? null) as ImportJobResultEnvelope | null}
              showCodes={false}
            />
            <ReportRowsGrid run={run} listingKey="projects.import.view::result-rows" />
          </>
        )}
      </TabsContent>
      <TabsContent value="values">
        <ValuesStep run={run} readOnly />
      </TabsContent>
      <TabsContent value="history">
        <AuditTrail entityType="project_import_run" entityId={run.id} />
      </TabsContent>
    </Tabs>
  );
}

export default ResultsView;
