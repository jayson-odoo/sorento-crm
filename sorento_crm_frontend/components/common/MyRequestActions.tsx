'use client';

import { Copy, Edit, RotateCcw, Send, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { MY_REQUEST_KEY } from '@/hooks/useMyRequests';
import { submitVerb } from '@/lib/submission-status';
import type { MyRequestKind } from '@/services/myRequestsService';

/** The forms whose draft `my_request.delete` deletes (`app/services/record_actions.py`). */
export type MyRequestDeleteKind = MyRequestKind | 'price_tag_request';

/**
 * The portal's action set on a salesperson's own request (PORTAL-P4-REQUESTS, owner Q2 a): Edit
 * and Submit while it is a draft or rejected, Delete while it is a draft, Revise when the server
 * allows it, Duplicate always. The submit label follows the shared rule (a rejected row is sent
 * back). The caller passes the status the portal reports (a request rejected at approval reads
 * "rejected").
 *
 * Delete parks `my_request.delete` on the server (D7): the button becomes a countdown with a
 * Cancel, and the server runs the portal's own draft delete when the window lapses.
 */
export function MyRequestActions({
  status,
  revisable,
  busy,
  kind,
  requestId,
  onEdit,
  onRevise,
  onDuplicate,
  onSubmit,
  onDeleted,
  invalidateKeys,
}: {
  status: string;
  revisable: boolean;
  busy: boolean;
  kind: MyRequestDeleteKind;
  requestId: string;
  onEdit: () => void;
  onRevise: () => void;
  onDuplicate: () => void;
  onSubmit: () => void;
  /** Where to go once the delete has committed: the page cannot stay on a deleted row. */
  onDeleted?: () => void;
  /** The staff list that showed the row, refetched once it is gone. */
  invalidateKeys?: readonly (readonly unknown[])[];
}) {
  const draft = status === 'draft';
  const open = draft || status === 'rejected';
  const remove = useDeferredAction({
    actionKey: 'my_request.delete',
    entityType: kind,
    entityId: requestId,
    verb: 'Deleting',
    subject: '',
    surface: 'inline',
    watchFromMount: draft,
    successMessage: 'Draft deleted',
    invalidateKeys: [[MY_REQUEST_KEY, kind], ...(invalidateKeys ?? [])],
    onCommitted: onDeleted,
  });
  return (
    <>
      {open && (
        <Button variant="outline" size="sm" onClick={onEdit} disabled={busy}>
          <Edit className="size-4" />
          Edit
        </Button>
      )}
      {draft && (
        <DeferredActionButton
          pending={remove.pending}
          verb="Deleting"
          onCancel={remove.cancel}
          idle={
            <Button
              variant="outline"
              size="sm"
              onClick={() => remove.start()}
              disabled={busy || remove.isPending || remove.isBlocked}
              className="text-destructive border-destructive/40 hover:bg-destructive/10"
            >
              <Trash2 className="size-4" />
              Delete
            </Button>
          }
        />
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
