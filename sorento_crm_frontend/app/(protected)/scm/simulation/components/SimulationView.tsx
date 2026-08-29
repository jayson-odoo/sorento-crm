'use client';

import { useMemo, useState } from 'react';
import { Database, DatabaseZap, GitCompare, LayoutGrid, Play, ShieldCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { fmtDateTime } from '../../lib/format';
import {
  useBlessBaseline,
  useRunSimulation,
  useScenarios,
  useSimulationOverview,
} from '../hooks/useSimulation';
import type { ScenarioStatus } from '../types/simulation.types';
import { BlessBaselineDialog } from './BlessBaselineDialog';
import { RunSimulationDialog } from './RunSimulationDialog';
import { ScenarioDiffSheet } from './ScenarioDiffSheet';
import { ScenariosGrid } from './ScenariosGrid';
import { SimulationPlanningTab } from './SimulationPlanningTab';

function fmtDate(iso: string | null): string {
  if (!iso) return 'never';
  return fmtDateTime(iso);
}

const COUNT_LABEL: Record<ScenarioStatus, string> = {
  SAME: 'same',
  CHANGED: 'changed',
  NEW: 'new',
  GONE: 'gone',
  NO_BASELINE: 'no baseline',
};

const COUNT_VARIANT: Record<ScenarioStatus, 'secondary' | 'warning' | 'info' | 'destructive'> = {
  SAME: 'secondary',
  CHANGED: 'warning',
  NEW: 'info',
  GONE: 'destructive',
  NO_BASELINE: 'secondary',
};

export function SimulationView() {
  const overview = useSimulationOverview();
  const scenarios = useScenarios();
  const runMutation = useRunSimulation();
  const blessMutation = useBlessBaseline();

  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [blessDialogOpen, setBlessDialogOpen] = useState(false);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  const rows = useMemo(() => scenarios.data ?? [], [scenarios.data]);
  const counts = useMemo(() => {
    const out: Record<ScenarioStatus, number> = {
      SAME: 0,
      CHANGED: 0,
      NEW: 0,
      GONE: 0,
      NO_BASELINE: 0,
    };
    for (const r of rows) out[r.status] += 1;
    return out;
  }, [rows]);

  const simDbActive = overview.data?.sim_db_active ?? false;

  return (
    <div className="space-y-4">
      <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        {overview.isLoading ? (
          <Skeleton className="h-6 w-72" />
        ) : (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {simDbActive ? (
              <Badge variant="success" appearance="light" size="lg">
                <Database className="size-3.5" />
                Sim DB
              </Badge>
            ) : (
              <Badge
                variant="warning"
                appearance="light"
                size="lg"
                title="This backend is not connected to the dedicated sim database - running is disabled."
              >
                <DatabaseZap className="size-3.5" />
                Not on sim DB - run disabled
              </Badge>
            )}
            <span className="text-muted-foreground">
              Baseline blessed {fmtDate(overview.data?.baseline_blessed_at ?? null)}
            </span>
            <span className="text-muted-foreground">
              Last run {fmtDate(overview.data?.current_run_at ?? null)}
            </span>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={!simDbActive || runMutation.isPending}
            onClick={() => setRunDialogOpen(true)}
          >
            <Play className="size-4" />
            Run simulation
          </Button>
          <Button
            disabled={!overview.data?.current_exists || blessMutation.isPending}
            onClick={() => setBlessDialogOpen(true)}
          >
            <ShieldCheck className="size-4" />
            Bless baseline
          </Button>
        </div>
      </Card>

      <Tabs defaultValue="diff" className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="diff">
            <GitCompare />
            <span>Baseline diff</span>
          </TabsTrigger>
          <TabsTrigger value="planning">
            <LayoutGrid />
            <span>Planning view</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="diff" className="mt-0 space-y-4 focus-visible:outline-none">
          {scenarios.isSuccess && rows.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {(Object.keys(COUNT_LABEL) as ScenarioStatus[]).map((status) => (
                <Badge key={status} variant={COUNT_VARIANT[status]} appearance="light" size="lg">
                  {counts[status]} {COUNT_LABEL[status]}
                </Badge>
              ))}
            </div>
          ) : null}

          {overview.isSuccess && !overview.data.baseline_exists && !overview.data.current_exists ? (
            <Card className="flex flex-col items-center gap-3 p-10 text-center">
              <p className="text-sm font-medium">No run has ever been blessed as a baseline.</p>
              <p className="text-2xs text-muted-foreground">
                Run the simulation once, inspect the result, then bless it - every future run is
                compared against whatever is blessed.
              </p>
            </Card>
          ) : (
            <ScenariosGrid
              rows={rows}
              isLoading={scenarios.isLoading}
              isError={scenarios.isError}
              error={scenarios.error as Error | null}
              onRetry={() => void scenarios.refetch()}
              onSelectRow={setSelectedCode}
            />
          )}
        </TabsContent>

        <TabsContent value="planning" className="mt-0 space-y-4 focus-visible:outline-none">
          <SimulationPlanningTab simDbActive={simDbActive} />
        </TabsContent>
      </Tabs>

      <ScenarioDiffSheet
        code={selectedCode}
        onOpenChange={(open) => {
          if (!open) setSelectedCode(null);
        }}
        simDbActive={simDbActive}
      />

      <RunSimulationDialog
        open={runDialogOpen}
        onOpenChange={setRunDialogOpen}
        pending={runMutation.isPending}
        onConfirm={() =>
          runMutation.mutate(false, { onSuccess: () => setRunDialogOpen(false) })
        }
      />

      <BlessBaselineDialog
        open={blessDialogOpen}
        onOpenChange={setBlessDialogOpen}
        pending={blessMutation.isPending}
        onConfirm={() =>
          blessMutation.mutate(undefined, { onSuccess: () => setBlessDialogOpen(false) })
        }
      />
    </div>
  );
}

export default SimulationView;
