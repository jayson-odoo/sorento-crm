'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
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
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useCertificateMergeTargets, useMergeCertificate } from '../hooks/useCertificates';
import type { Certificate } from '../types/certificate.types';

/**
 * "Merge as a revision of ..." (DUP-4/DUP-6). Two steps: pick the target, then
 * confirm in an AlertDialog that names BOTH certificates and the number of
 * revisions being moved. Compliance history moves, so this is never one click.
 */
export default function CertificateMergeDialog({
  open,
  onOpenChange,
  certificate,
  onMerged,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  certificate: Certificate;
  onMerged: (targetId: string) => void;
}) {
  const [step, setStep] = useState<'pick' | 'confirm'>('pick');
  const [targetId, setTargetId] = useState('');
  const { data: targets = [], isLoading } = useCertificateMergeTargets(open ? certificate.id : null);
  const mergeMutation = useMergeCertificate();

  useEffect(() => {
    if (open) {
      setStep('pick');
      setTargetId(certificate.possible_duplicate_of_certificate_id ?? '');
    }
  }, [open, certificate.possible_duplicate_of_certificate_id]);

  const sourceLabel = `${certificate.scheme} ${certificate.certificate_number}`;
  const revisionCount = (certificate.revisions ?? []).length;
  const target = targets.find((t) => t.value === targetId);

  const close = () => {
    onOpenChange(false);
    setStep('pick');
  };

  return (
    <>
      <Dialog open={open && step === 'pick'} onOpenChange={(next) => !next && close()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Merge {sourceLabel} as a revision</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Merge into</Label>
              <SearchableSelect
                value={targetId}
                onChange={setTargetId}
                options={targets}
                placeholder={isLoading ? 'Loading certificates...' : 'Select a certificate'}
                emptyMessage="No other certificate on this scheme."
                disabled={isLoading}
                triggerClassName="mt-1"
              />
            </div>
            <p className="text-sm text-muted-foreground">
              {revisionCount} revision{revisionCount === 1 ? '' : 's'} and{' '}
              {certificate.covered_product_count} covered product
              {certificate.covered_product_count === 1 ? '' : 's'} will move across.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={close}>
              Cancel
            </Button>
            <Button disabled={!targetId} onClick={() => setStep('confirm')}>
              Continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={open && step === 'confirm'}
        onOpenChange={(next) => !next && setStep('pick')}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm merge</AlertDialogTitle>
            <AlertDialogDescription>
              {sourceLabel} will be merged into {target?.label ?? 'the selected certificate'}.{' '}
              {revisionCount} revision{revisionCount === 1 ? '' : 's'} and its covered products move
              across, and {sourceLabel} is deleted. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={mergeMutation.isPending}
              onClick={(e) => {
                e.preventDefault();
                mergeMutation.mutate(
                  { id: certificate.id, targetId },
                  {
                    onSuccess: () => {
                      close();
                      onMerged(targetId);
                    },
                  },
                );
              }}
            >
              {mergeMutation.isPending && <Loader2 className="me-2 size-4 animate-spin" />}
              Merge
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
