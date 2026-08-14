'use client';

import { CalendarDays, ServerOff } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Code } from '@/components/ui/code';
import { Skeleton } from '@/components/ui/skeleton';
import { PlanLinesSection } from '../../reorder/components/PlanLinesSection';
import { useTodayRun } from '../../reorder/hooks/useReorderRun';

const SERVE_COMMAND = 'venv/bin/python -m scripts.scm_sim serve --port 8064';

/**
 * The REAL Reorder Planning grid - `PlanLinesSection` (PlanLinesGrid + PlanBudgetReview +
 * LevelChangesPanel, all driven by `usePlanLines`) - scoped to whichever run is on the sim
 * database. Run resolution reuses `useTodayRun` UNCHANGED, the same hook the reorder page
 * itself opens to ("today's plan, else the most-recent completed run"): a scenario run
 * picked up here is resolved identically to how the real page would resolve it, since it is
 * the same code, not a re-implementation (standing rule: one render source, or tooltips and
 * popovers drift between screens).
 *
 * Gated on `simDbActive` (from `/scm/simulation/overview`) so this tab never renders the
 * real dev-DB plan through a backend that happens not to be pointed at the sim database.
 */
export function SimulationPlanningTab({ simDbActive }: { simDbActive: boolean }) {
  const today = useTodayRun();

  if (!simDbActive) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <ServerOff className="size-5" aria-hidden />
        </span>
        <p className="text-sm font-medium">
          The planning view needs the backend on the sim database.
        </p>
        <Code showCopyButton copyText={SERVE_COMMAND} size="sm">
          {SERVE_COMMAND}
        </Code>
      </Card>
    );
  }

  if (today.isLoading) {
    return <Skeleton className="h-72 w-full rounded-xl" />;
  }

  if (today.isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <p className="text-sm text-muted-foreground">
          {today.error instanceof Error ? today.error.message : 'Failed to load the sim run.'}
        </p>
      </Card>
    );
  }

  if (!today.data) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <CalendarDays className="size-5" aria-hidden />
        </span>
        <p className="text-sm font-medium">No sim run yet.</p>
      </Card>
    );
  }

  return <PlanLinesSection runId={today.data.run_id} />;
}
