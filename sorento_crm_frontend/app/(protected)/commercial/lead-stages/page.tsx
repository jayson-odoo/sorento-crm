'use client';

import { useMemo } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { Card, CardContent, CardHeader, CardTable, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useDeleteLeadStage, useLeadStagesList, useUpdateLeadStage } from '../leads/hooks/useLeadStages';
import { useHasPermission } from '@/hooks/usePermissions';
import { useState } from 'react';

export default function LeadStagesPage() {
  const { data: stages = [], isLoading, refetch } = useLeadStagesList();
  const updateStage = useUpdateLeadStage();
  const deleteStageMutation = useDeleteLeadStage();
  const canEdit = useHasPermission('commercial_core.lead_stages.edit');
  const canDelete = useHasPermission('commercial_core.lead_stages.delete');
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const sorted = useMemo(
    () => [...stages].sort((a, b) => a.sort_order - b.sort_order || a.stage_code.localeCompare(b.stage_code)),
    [stages],
  );

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Lead stages</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Commercial</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              Refresh
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <Card>
          <CardHeader>
            <CardTitle>Stages</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <CardTable>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Code</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Order</TableHead>
                    <TableHead>Terminal</TableHead>
                    <TableHead>Allows conversion</TableHead>
                    {canDelete && <TableHead className="w-[100px]" />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading && (
                    <TableRow>
                      <TableCell colSpan={6}>Loading…</TableCell>
                    </TableRow>
                  )}
                  {!isLoading &&
                    sorted.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="font-mono text-sm">{s.stage_code}</TableCell>
                        <TableCell>{s.stage_name}</TableCell>
                        <TableCell>{s.sort_order}</TableCell>
                        <TableCell>
                          <Switch
                            checked={s.is_terminal}
                            disabled={!canEdit}
                            onCheckedChange={(v) =>
                              updateStage.mutate({ id: s.id, data: { is_terminal: v } })
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Switch
                            checked={s.allows_conversion}
                            disabled={!canEdit}
                            onCheckedChange={(v) =>
                              updateStage.mutate({ id: s.id, data: { allows_conversion: v } })
                            }
                          />
                        </TableCell>
                        {canDelete && (
                          <TableCell>
                            <Button variant="ghost" size="sm" onClick={() => setPendingDeleteId(s.id)}>
                              Delete
                            </Button>
                          </TableCell>
                        )}
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </CardTable>
          </CardContent>
        </Card>
      </Container>

      <ConfirmDeleteDialog
        open={!!pendingDeleteId}
        onOpenChange={(o) => !o && setPendingDeleteId(null)}
        description="Delete this stage? It must not be assigned to any lead."
        onDelete={async () => {
          if (!pendingDeleteId) return;
          await deleteStageMutation.mutateAsync(pendingDeleteId);
        }}
        onSuccess={() => setPendingDeleteId(null)}
      />
    </>
  );
}
