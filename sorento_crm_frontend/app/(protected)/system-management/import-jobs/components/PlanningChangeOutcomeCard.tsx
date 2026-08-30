'use client';

import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { OutstandingPlanningChangeBatch } from '../../../scm/reorder/services/outstandingImportService';

/**
 * The planning-change batch an outstanding sales-order book upload raised
 * (`PLAN-so-book-diff-replanning.md` AC-R01), once the worker has actually run it.
 *
 * The upload dialog's own card (`OutstandingUploadDialog.tsx`) reads `preview.
 * planning_change_batch`, which is populated only when the TEST response carries one; the
 * real write happens on the worker after Confirm, so this job page - where every other
 * importer reports what it did - is where a real upload's batch is actually seen. Read off
 * `result.upload.planning_change_batch`, the job's own result envelope (see
 * `_run_scm_upload_job` in `import_tasks.py`, which nests the channel's own answer under
 * `upload`).
 */
export function PlanningChangeOutcomeCard({
  batch,
}: {
  batch: OutstandingPlanningChangeBatch;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Planning changes</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm">
            {`This upload moved ${batch.line_count.toLocaleString()} planned line${
              batch.line_count === 1 ? '' : 's'
            } on ${batch.order_count.toLocaleString()} order${
              batch.order_count === 1 ? '' : 's'
            }`}
          </p>
          {/* The LIST, not a batch page: a book upload moves lines on many orders at once,
              and the board is addressed with the orders it is to show (AC-P3-1). The list row
              carries them and its Plan action opens the board on them. */}
          <Button asChild variant="outline" size="sm">
            <Link href="/project-sales/planning-changes">Review</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default PlanningChangeOutcomeCard;
