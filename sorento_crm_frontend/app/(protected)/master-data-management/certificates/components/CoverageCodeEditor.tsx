'use client';

import { useState } from 'react';
import { Pencil } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useUpdateCertificateProductCode } from '../hooks/useCertificates';

/**
 * The code printed on the certificate for one covered product; with the edit right the text can
 * be typed over in place. A code the system read itself (`ai`) looks like any other: there is no
 * Suggested badge or Confirm tick (CERT-TAB-UX, owner 11 Nov 2026: the red box is the check).
 */
export function CoverageCodeEditor(props: CoverageCodeProps) {
  // The editable form holds the save mutation; a viewer's cell needs no hooks at all.
  return props.canEdit ? <EditableCoverageCode {...props} /> : <CoverageCodeText {...props} />;
}

interface CoverageCodeProps {
  certificateId: string;
  coverageId: string;
  code: string | null | undefined;
  source: 'ai' | 'manual' | null | undefined;
  canEdit: boolean;
  onSaved?: () => void;
}

function CoverageCodeText({ code }: CoverageCodeProps) {
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <span className="truncate" title={code ?? undefined}>
        {code || '-'}
      </span>
    </div>
  );
}

function EditableCoverageCode({
  certificateId,
  coverageId,
  code,
  canEdit,
  onSaved,
}: CoverageCodeProps) {
  const update = useUpdateCertificateProductCode();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const save = (body: { model_code?: string | null }) =>
    update.mutate(
      { id: certificateId, coverageId, body },
      {
        onSuccess: () => {
          setEditing(false);
          onSaved?.();
        },
      },
    );

  if (editing) {
    return (
      <form
        className="flex items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          save({ model_code: draft });
        }}
      >
        <Input
          autoFocus
          variant="sm"
          value={draft}
          maxLength={60}
          aria-label="Code on certificate"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && setEditing(false)}
        />
        <Button type="submit" size="sm" disabled={update.isPending}>
          Save
        </Button>
      </form>
    );
  }

  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <span className="truncate" title={code ?? undefined}>
        {code || '-'}
      </span>
      {canEdit && (
        <Button
          mode="icon"
          variant="dim"
          size="sm"
          aria-label="Edit code on certificate"
          onClick={() => {
            setDraft(code ?? '');
            setEditing(true);
          }}
        >
          <Pencil className="size-4" />
        </Button>
      )}
    </div>
  );
}
