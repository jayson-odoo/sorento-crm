'use client';

import { use, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Pencil } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { useConfigStageByCode, useDeleteConfigStage } from '../../../hooks/useConfigStages';
import type { ConfigStageResource } from '../../../services/configStageService';

function isResource(s: string): s is ConfigStageResource {
  return s === 'tender-stages' || s === 'master-quotation-stages' || s === 'task-statuses';
}

export default function ConfigStageDetailPage({
  params,
}: {
  params: Promise<{ resource: string; code: string }>;
}) {
  const { resource, code } = use(params);
  const router = useRouter();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const stageCode = decodeURIComponent(code);

  if (!isResource(resource)) {
    return null;
  }

  const { data: row, isLoading } = useConfigStageByCode(resource, stageCode);
  const del = useDeleteConfigStage(resource);
  const base = `/commercial-core/process-configuration/stages/${resource}`;

  const handleDelete = async () => {
    await del.mutateAsync(stageCode);
    setConfirmOpen(false);
    router.push(base);
  };

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Stage</ToolbarTitle>
          </ToolbarHeading>
          {/* @ts-expect-error: sorento ToolbarActions does not yet accept className. */}
          <ToolbarActions className="gap-2">
            <Button variant="outline" asChild>
              <Link href={base}>Back</Link>
            </Button>
            <Button asChild>
              <Link href={`${base}/${encodeURIComponent(stageCode)}/edit`}>
                <Pencil className="size-4" />
                Edit
              </Link>
            </Button>
            <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
              Delete
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>
      <Container>
        {isLoading || !row ? (
          <div className="flex justify-center py-12">
            <LoaderCircleIcon className="size-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>{row.stage_name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="text-muted-foreground">Code:</span> {row.stage_code}
              </p>
              <p>
                <span className="text-muted-foreground">Sort order:</span> {row.sort_order}
              </p>
              <p>
                <span className="text-muted-foreground">Active:</span> {row.is_active ? 'Yes' : 'No'}
              </p>
              <p>
                <span className="text-muted-foreground">Terminal:</span> {row.is_terminal ? 'Yes' : 'No'}
              </p>
              {row.description ? (
                <p>
                  <span className="text-muted-foreground">Description:</span> {row.description}
                </p>
              ) : null}
            </CardContent>
          </Card>
        )}
      </Container>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this stage? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => void handleDelete()}
              disabled={del.isPending}
            >
              {del.isPending ? 'Deleting…' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
