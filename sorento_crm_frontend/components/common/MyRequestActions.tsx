'use client';

import { Copy, Edit, RotateCcw, Send, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { submitVerb } from '@/lib/submission-status';

/**
 * The portal's action set on a salesperson's own request (PORTAL-P4-REQUESTS, owner Q2 a): Edit
 * and Submit while it is a draft or rejected, Delete while it is a draft, Revise when the server
 * allows it, Duplicate always. The submit label follows the shared rule (a rejected row is sent
 * back). The caller passes the status the portal reports (a request rejected at approval reads
 * "rejected").
 */
export function MyRequestActions({
  status,
  revisable,
  busy,
  onEdit,
  onRevise,
  onDuplicate,
  onDelete,
  onSubmit,
}: {
  status: string;
  revisable: boolean;
  busy: boolean;
  onEdit: () => void;
  onRevise: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onSubmit: () => void;
}) {
  const draft = status === 'draft';
  const open = draft || status === 'rejected';
  return (
    <>
      {open && (
        <Button variant="outline" size="sm" onClick={onEdit} disabled={busy}>
          <Edit className="size-4" />
          Edit
        </Button>
      )}
      {draft && (
        <Button
          variant="outline"
          size="sm"
          onClick={onDelete}
          disabled={busy}
          className="text-destructive border-destructive/40 hover:bg-destructive/10"
        >
          <Trash2 className="size-4" />
          Delete
        </Button>
      )}
      {revisable && (
        <Button variant="outline" size="sm" onClick={onRevise} disabled={busy}>
          <RotateCcw className="size-4" />
          Revise
        </Button>
      )}
      <Button variant="outline" size="sm" onClick={onDuplicate} disabled={busy}>
        <Copy className="size-4" />
        Duplicate
      </Button>
      {open && (
        <Button variant="primary" size="sm" onClick={onSubmit} disabled={busy}>
          <Send className="size-4" />
          {submitVerb(status)}
        </Button>
      )}
    </>
  );
}
