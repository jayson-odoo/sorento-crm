'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { toast } from '@/lib/toast';
import { useProjectImportMutations } from '../../_shared/hooks/useProjectImport';
import type { ProjectImportRun } from '../../_shared/types/projectImport.types';

/**
 * Create (AC-PI-44): drop the workbook, tick its sheets, then Next opens the run page.
 * The upload itself reads the sheets, so the ticks show real row counts.
 */
export function CreateImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [files, setFiles] = React.useState<File[]>([]);
  const [run, setRun] = React.useState<ProjectImportRun | null>(null);
  const [ticked, setTicked] = React.useState<string[]>([]);
  const { create } = useProjectImportMutations();
  const { columns } = useProjectImportMutations(run?.id);

  React.useEffect(() => {
    if (!open) {
      setFiles([]);
      setRun(null);
      setTicked([]);
    }
  }, [open]);

  const upload = async () => {
    const file = files[0];
    if (!file) return;
    const made = await create.mutateAsync(file).catch(() => null);
    if (!made) return;
    setRun(made);
    setTicked(made.sheets.filter((s) => s.ticked ?? s.has_ps_heading).map((s) => s.name));
  };

  const next = async () => {
    if (!run) return;
    const saved = await columns
      .mutateAsync({ sheets: ticked, columns: run.columns })
      .catch(() => null);
    if (!saved) return;
    onOpenChange(false);
    router.push(`/project-sales/import/${run.id}`);
  };

  const busy = create.isPending || columns.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-full max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>New project import</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {!run ? (
            <FileDropzone
              accept=".xlsx"
              maxSizeMb={10}
              files={files}
              onFilesChange={setFiles}
              onReject={(_file, reason) =>
                toast.error(reason === 'size' ? 'The file is larger than 10 MB.' : 'Upload an Excel workbook (.xlsx).')
              }
              title="Drop the workbook here"
              aria-label="Workbook"
            />
          ) : (
            <ul className="space-y-2" aria-label="Sheets">
              {run.sheets.map((sheet) => {
                const checked = ticked.includes(sheet.name);
                return (
                  <li key={sheet.name} className="flex items-center gap-3">
                    <Checkbox
                      id={`sheet-${sheet.name}`}
                      checked={checked}
                      disabled={!sheet.has_ps_heading}
                      onCheckedChange={(on) =>
                        setTicked((prev) =>
                          on ? [...prev, sheet.name] : prev.filter((n) => n !== sheet.name),
                        )
                      }
                    />
                    <label htmlFor={`sheet-${sheet.name}`} className="flex-1 truncate text-sm">
                      {sheet.name_trimmed}
                    </label>
                    <span className="text-sm text-muted-foreground">
                      {sheet.has_ps_heading ? `${sheet.row_count} rows` : 'No PS numbers'}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          {!run ? (
            <Button onClick={() => void upload()} disabled={!files.length || busy}>
              {create.isPending ? 'Reading…' : 'Upload'}
            </Button>
          ) : (
            <Button onClick={() => void next()} disabled={!ticked.length || busy}>
              Next
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default CreateImportDialog;
