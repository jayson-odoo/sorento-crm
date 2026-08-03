'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { FileDropzone } from '@/components/common/FileDropzone';
import { toast } from 'sonner';
import { listParties } from '../../_shared/services/projectService';
import { usePurchaseOrders } from '../../_shared/hooks/useProjects';
import { useDeliveryScheduleMutations } from '../../_shared/hooks/useDeliverySchedules';
import type { DeliverySchedule } from '../../_shared/types/deliverySchedule.types';
import type { Project } from '../../_shared/types/project.types';

const ACCEPTED = '.pdf,.jpg,.jpeg,.png';

/**
 * Upload a delivery schedule against a PO.
 *
 * The PO is asked for because the PO version is what the column totals are reconciled
 * AGAINST, and the issuer is asked rather than assumed: on the client's own documents R2 was
 * issued by a different company than the one that raised the PO.
 */
export function DeliveryScheduleUploadDialog({
  project,
  schedules,
  onDone,
}: {
  project: Project;
  schedules: DeliverySchedule[];
  onDone: () => void;
}) {
  const router = useRouter();
  const purchaseOrders = usePurchaseOrders(project.id);
  const { upload } = useDeliveryScheduleMutations(project.id);

  const [poId, setPoId] = React.useState('');
  const [scheduleId, setScheduleId] = React.useState('');
  const [issuerId, setIssuerId] = React.useState('');
  const [revisionLabel, setRevisionLabel] = React.useState('');
  const [file, setFile] = React.useState<File | null>(null);

  const poRows = React.useMemo(() => purchaseOrders.data ?? [], [purchaseOrders.data]);

  // One PO is the normal case, so pick it rather than making the user confirm the obvious.
  React.useEffect(() => {
    if (!poId && poRows.length === 1) setPoId(poRows[0].id);
  }, [poId, poRows]);

  const existingForPo = React.useMemo(
    () => schedules.filter((schedule) => schedule.purchase_order_id === poId),
    [schedules, poId],
  );

  // Changing the PO invalidates a schedule chosen under the previous one.
  React.useEffect(() => {
    if (scheduleId && !existingForPo.some((schedule) => schedule.id === scheduleId)) {
      setScheduleId('');
    }
  }, [existingForPo, scheduleId]);

  const fetchParties = React.useCallback(async (query: string) => {
    const body = await listParties({ query: query || undefined, limit: 50 });
    return body.data.map((party) => ({
      value: party.id,
      label: party.name,
      description: party.registration_no ?? undefined,
    }));
  }, []);

  const blocked = !poId || !file || upload.isPending;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Upload a delivery schedule</DialogTitle>
          <DialogDescription>
            PDF or a photo. Reading it takes a moment and you can watch it happen.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!file || !poId) return;
            const result = await upload.mutateAsync({
              poId,
              body: {
                file,
                issuer_party_id: issuerId || null,
                revision_label: revisionLabel.trim() || null,
                delivery_schedule_id: scheduleId || null,
              },
            });
            onDone();
            router.push(
              `/project-sales/${project.id}/delivery-schedules/${result.schedule_version_id}`,
            );
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="schedule-po">
                Purchase order <span className="text-destructive">*</span>
              </Label>
              <SearchableSelect
                id="schedule-po"
                value={poId}
                onChange={setPoId}
                options={poRows.map((po) => ({
                  value: po.id,
                  label: po.po_number,
                  description: po.issuing_party_name ?? undefined,
                }))}
                placeholder="Which PO is this schedule for"
                emptyMessage="No purchase orders on this project"
              />
            </div>

            {existingForPo.length > 0 && (
              <div className="space-y-1.5">
                <Label htmlFor="schedule-existing">Revision of</Label>
                <SearchableSelect
                  id="schedule-existing"
                  value={scheduleId}
                  onChange={setScheduleId}
                  clearable
                  options={existingForPo.map((schedule) => ({
                    value: schedule.id,
                    label:
                      schedule.latest_revision_label ??
                      `${schedule.po_number ?? 'Schedule'} v${schedule.latest_version_no ?? 1}`,
                    description: `${schedule.version_count} version${
                      schedule.version_count === 1 ? '' : 's'
                    } so far`,
                  }))}
                  placeholder="A schedule we have not seen before"
                />
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="schedule-issuer">Issued by</Label>
              <SearchableSelect
                id="schedule-issuer"
                value={issuerId}
                onChange={setIssuerId}
                clearable
                fetchOptions={fetchParties}
                placeholder="The company whose letterhead it carries"
                emptyMessage="No parties match"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="schedule-revision">Revision label</Label>
              <Input
                id="schedule-revision"
                value={revisionLabel}
                onChange={(event) => setRevisionLabel(event.target.value)}
                placeholder="As printed, e.g. REVISED 1 - 23/7/2026"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="schedule-file">
                File <span className="text-destructive">*</span>
              </Label>
              <FileDropzone
                id="schedule-file"
                accept={ACCEPTED}
                files={file ? [file] : []}
                onFilesChange={(files) => setFile(files[0] ?? null)}
                onReject={(rejected, reason) =>
                  toast.error(
                    reason === 'type'
                      ? `${rejected.name} is not a PDF or a photo.`
                      : `${rejected.name} is larger than 25 MB.`,
                  )
                }
                maxSizeMb={25}
                title="Drop the delivery schedule here"
                hint="PDF or photo"
                aria-label="Delivery schedule document"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={blocked}>
              {upload.isPending ? 'Uploading…' : 'Upload'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
