'use client';

import { useState } from 'react';
import { Check, Pencil } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useUpdateCertificateProductCode } from '../hooks/useCertificates';

/**
 * The code printed on the certificate for one covered product. A Suggested code (read by the
 * system) shows a badge and Confirm; with the edit right the text can be typed over in place.
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

function CoverageCodeText({ code, source }: CoverageCodeProps) {
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <span className="truncate" title={code ?? undefined}>
        {code || '-'}
      </span>
      {code && source === 'ai' && (
        <Badge variant="warning" appearance="light" size="sm" className="shrink-0">
          Suggested
        </Badge>
      )}
    </div>
  );
}

function EditableCoverageCode({
  certificateId,
  coverageId,
  code,
  source,
  canEdit,
  onSaved,
}: CoverageCodeProps) {
  const update = useUpdateCertificateProductCode();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const save = (body: { model_code?: string | null; confirm?: boolean }) =>
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
      {code && source === 'ai' && (
        <Badge variant="warning" appearance="light" size="sm" className="shrink-0">
          Suggested
        </Badge>
      )}
      {canEdit && code && source === 'ai' && (
        <Button
          mode="icon"
          variant="dim"
          size="sm"
          aria-label="Confirm code"
          disabled={update.isPending}
          onClick={() => save({ confirm: true })}
        >
          <Check className="size-4" />
        </Button>
      )}
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
