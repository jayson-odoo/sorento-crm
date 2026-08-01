'use client';

import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Edit, Plus, Trash2 } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useStatusEntities, useStatusGraph } from '../hooks/useStatusGraphs';
import type { Status, StatusTransition } from '../types/statusGraph.types';
import StatusDeleteDialog from './StatusDeleteDialog';
import StatusFormDialog from './StatusFormDialog';
import TransitionDeleteDialog from './TransitionDeleteDialog';
import TransitionFormDialog from './TransitionFormDialog';

export default function StatusGraphsClient() {
  const [entityType, setEntityType] = useState('');
  const [statusFormOpen, setStatusFormOpen] = useState(false);
  const [editingStatus, setEditingStatus] = useState<Status | undefined>();
  const [deletingStatus, setDeletingStatus] = useState<Status | null>(null);
  const [transitionFormOpen, setTransitionFormOpen] = useState(false);
  const [editingTransition, setEditingTransition] = useState<StatusTransition | undefined>();
  const [deletingTransition, setDeletingTransition] = useState<StatusTransition | null>(null);

  const entitiesQuery = useStatusEntities();
  const entities = entitiesQuery.data ?? [];

  // Default to the first entity once they load, so the page is never a dead end.
  useEffect(() => {
    if (!entityType && entities.length > 0) setEntityType(entities[0].entity_type);
  }, [entities, entityType]);

  const graphQuery = useStatusGraph(entityType || undefined, null, true);
  const graph = graphQuery.data;
  const statuses = useMemo(() => graph?.statuses ?? [], [graph]);
  const transitions = useMemo(() => graph?.transitions ?? [], [graph]);
  const statusById = useMemo(
    () => new Map(statuses.map((s) => [s.id, s])),
    [statuses],
  );

  const selectedEntity = entities.find((e) => e.entity_type === entityType);

  if (entitiesQuery.isLoading) {
    return <LoadingCard message="Loading status entities..." />;
  }

  if (entitiesQuery.isError) {
    return (
      <EmptyCard
        title="Could not load status entities"
        body={(entitiesQuery.error as Error)?.message ?? 'Something went wrong.'}
      />
    );
  }

  // No module has registered an entity yet. This is the expected state on a fresh
  // install, so it gets an explanation rather than a blank screen.
  if (entities.length === 0) {
    return (
      <EmptyCard
        title="No entities use configurable statuses yet"
        body="Status graphs are set up per entity, and an entity appears here once a module registers it. Install or enable a module that uses the status engine to start configuring one."
      />
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6 sm:flex-row sm:items-end">
          <div className="grid min-w-0 flex-1 gap-2">
            <Label>Entity</Label>
            <SearchableSelect
              value={entityType}
              onChange={setEntityType}
              options={entities.map((e) => ({ value: e.entity_type, label: e.label }))}
              placeholder="Pick an entity"
              triggerClassName="w-full sm:w-80"
            />
          </div>
          {selectedEntity && (
            <p className="text-sm text-muted-foreground">
              Provided by the <span className="font-medium">{selectedEntity.module}</span> module.
              {selectedEntity.supports_scoped_graphs && selectedEntity.scope_label
                ? ` Each ${selectedEntity.scope_label.toLowerCase()} can override this graph.`
                : ''}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>Statuses</CardTitle>
          <Button size="sm" onClick={() => { setEditingStatus(undefined); setStatusFormOpen(true); }}>
            <Plus className="size-4" />
            Add status
          </Button>
        </CardHeader>
        <CardContent>
          {graphQuery.isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Loading graph...</p>
          ) : statuses.length === 0 ? (
            <div className="py-8 text-center">
              <p className="text-sm font-medium">This entity has no statuses yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Add the first one and mark it as the starting state, then connect the rest with
                transitions.
              </p>
            </div>
          ) : (
            <ScrollArea>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="px-3 py-2 text-left font-medium">Label</th>
                    <th className="px-3 py-2 text-left font-medium">Key</th>
                    <th className="px-3 py-2 text-left font-medium">Flags</th>
                    <th className="px-3 py-2 text-left font-medium">Records</th>
                    <th className="px-3 py-2 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {statuses.map((status) => (
                    <tr key={status.id} className="border-b last:border-0">
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-2">
                          {status.color_hex && (
                            <span
                              aria-hidden
                              className="size-2.5 shrink-0 rounded-full"
                              style={{ backgroundColor: status.color_hex }}
                            />
                          )}
                          <span className="truncate font-medium" title={status.label}>
                            {status.label}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <code className="text-xs text-muted-foreground">{status.key}</code>
                      </td>
                      <td className="px-3 py-2">
                        <span className="flex flex-wrap gap-1">
                          {status.is_initial && (
                            <Badge variant="primary" size="sm" appearance="ghost">Start</Badge>
                          )}
                          {status.is_terminal && (
                            <Badge variant="secondary" size="sm" appearance="ghost">Final</Badge>
                          )}
                          {!status.is_active && (
                            <Badge variant="warning" size="sm" appearance="ghost">
                              <BadgeDot />
                              Inactive
                            </Badge>
                          )}
                          {status.is_system && (
                            <Badge variant="secondary" size="sm" appearance="ghost">System</Badge>
                          )}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant="secondary" size="sm" className="w-fit">
                          {status.record_count ?? 0}
                        </Badge>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            mode="icon"
                            variant="ghost"
                            size="sm"
                            title="Edit"
                            onClick={() => { setEditingStatus(status); setStatusFormOpen(true); }}
                          >
                            <Edit className="size-4" />
                          </Button>
                          <Button
                            mode="icon"
                            variant="ghost"
                            size="sm"
                            title={status.is_system ? 'System statuses cannot be deleted' : 'Delete'}
                            disabled={status.is_system}
                            onClick={() => setDeletingStatus(status)}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <CardTitle>Transitions</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              The only moves allowed. Anything not listed here is refused, whatever the screen
              offers.
            </p>
          </div>
          <Button
            size="sm"
            disabled={statuses.length < 2}
            title={statuses.length < 2 ? 'Add at least two statuses first' : undefined}
            onClick={() => { setEditingTransition(undefined); setTransitionFormOpen(true); }}
          >
            <Plus className="size-4" />
            Add transition
          </Button>
        </CardHeader>
        <CardContent>
          {graphQuery.isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Loading graph...</p>
          ) : transitions.length === 0 ? (
            <div className="py-8 text-center">
              <p className="text-sm font-medium">No transitions yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {statuses.length < 2
                  ? 'Add at least two statuses, then connect them.'
                  : 'Nothing can move between these statuses until you connect them.'}
              </p>
            </div>
          ) : (
            <ScrollArea>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="px-3 py-2 text-left font-medium">Move</th>
                    <th className="px-3 py-2 text-left font-medium">Label</th>
                    <th className="px-3 py-2 text-left font-medium">Trigger</th>
                    <th className="px-3 py-2 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {transitions.map((transition) => {
                    const isAuto = transition.trigger_mode === 'auto';
                    return (
                      <tr key={transition.id} className="border-b last:border-0">
                        <td className="px-3 py-2">
                          <span className="flex items-center gap-2">
                            <span className="truncate">
                              {statusById.get(transition.from_status_id)?.label ?? 'Unknown'}
                            </span>
                            <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
                            <span className="truncate">
                              {statusById.get(transition.to_status_id)?.label ?? 'Unknown'}
                            </span>
                          </span>
                        </td>
                        <td className="px-3 py-2 truncate" title={transition.label}>
                          {transition.label}
                        </td>
                        <td className="px-3 py-2">
                          {isAuto ? (
                            <Badge
                              variant="info"
                              size="sm"
                              appearance="ghost"
                              title="Fired by the system when its conditions are met. Configured in code."
                            >
                              Automatic
                            </Badge>
                          ) : (
                            <Badge variant="secondary" size="sm" appearance="ghost">
                              Manual
                            </Badge>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              mode="icon"
                              variant="ghost"
                              size="sm"
                              title={isAuto ? 'Automatic transitions are configured in code' : 'Edit'}
                              disabled={isAuto}
                              onClick={() => {
                                setEditingTransition(transition);
                                setTransitionFormOpen(true);
                              }}
                            >
                              <Edit className="size-4" />
                            </Button>
                            <Button
                              mode="icon"
                              variant="ghost"
                              size="sm"
                              title={isAuto ? 'Automatic transitions are configured in code' : 'Delete'}
                              disabled={isAuto}
                              onClick={() => setDeletingTransition(transition)}
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {entityType && (
        <>
          <StatusFormDialog
            open={statusFormOpen}
            onOpenChange={(open) => {
              setStatusFormOpen(open);
              if (!open) setEditingStatus(undefined);
            }}
            entityType={entityType}
            scopeId={null}
            status={editingStatus}
          />
          <TransitionFormDialog
            open={transitionFormOpen}
            onOpenChange={(open) => {
              setTransitionFormOpen(open);
              if (!open) setEditingTransition(undefined);
            }}
            entityType={entityType}
            scopeId={null}
            statuses={statuses}
            transition={editingTransition}
          />
          {deletingStatus && (
            <StatusDeleteDialog
              open
              onOpenChange={(open) => !open && setDeletingStatus(null)}
              entityType={entityType}
              scopeId={null}
              status={deletingStatus}
              siblings={statuses.filter((s) => s.id !== deletingStatus.id)}
            />
          )}
          {deletingTransition && (
            <TransitionDeleteDialog
              open
              onOpenChange={(open) => !open && setDeletingTransition(null)}
              entityType={entityType}
              scopeId={null}
              transition={deletingTransition}
              fromLabel={statusById.get(deletingTransition.from_status_id)?.label ?? 'Unknown'}
              toLabel={statusById.get(deletingTransition.to_status_id)?.label ?? 'Unknown'}
            />
          )}
        </>
      )}
    </div>
  );
}

function LoadingCard({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="py-12 text-center text-sm text-muted-foreground">
        {message}
      </CardContent>
    </Card>
  );
}

function EmptyCard({ title, body }: { title: string; body: string }) {
  return (
    <Card>
      <CardContent className="py-12 text-center">
        <p className="text-sm font-medium">{title}</p>
        <p className="mx-auto mt-2 max-w-prose text-sm text-muted-foreground">{body}</p>
      </CardContent>
    </Card>
  );
}
