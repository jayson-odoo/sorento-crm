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
import { useLeadStageByCode, useDeleteLeadStageByCode } from '@/app/(protected)/commercial/leads/hooks/useLeadStages';

export default function LeadStageDetailPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const stageCode = decodeURIComponent(code);
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { data: row, isLoading } = useLeadStageByCode(stageCode);
  const del = useDeleteLeadStageByCode();

  return (
    <>
      <div className="mb-4 flex gap-2">
        <Button variant="outline" asChild>
          <Link href="/commercial-core/process-configuration/lead-stages">Back</Link>
        </Button>
        <Button asChild>
          <Link href={`/commercial-core/process-configuration/lead-stages/${encodeURIComponent(stageCode)}/edit`}>
            <Pencil className="size-4" />
            Edit
          </Link>
        </Button>
        <Button variant="destructive" onClick={() => setOpen(true)}>
          Delete
        </Button>
      </div>
      {isLoading || !row ? (
        <LoaderCircleIcon className="mx-auto size-8 animate-spin text-muted-foreground" />
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
              <span className="text-muted-foreground">Terminal:</span> {row.is_terminal ? 'Yes' : 'No'}
            </p>
            <p>
              <span className="text-muted-foreground">Allows conversion:</span> {row.allows_conversion ? 'Yes' : 'No'}
            </p>
          </CardContent>
        </Card>
      )}

      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this lead stage? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={async () => {
                await del.mutateAsync(stageCode);
                setOpen(false);
                router.push('/commercial-core/process-configuration/lead-stages');
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
