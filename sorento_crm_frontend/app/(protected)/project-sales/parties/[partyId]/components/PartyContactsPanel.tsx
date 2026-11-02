'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  PARTIES_KEY,
  partyContactsKey,
  usePartyContacts,
} from '../../../_shared/hooks/useProjects';
import type { PartyContact } from '../../../_shared/types/project.types';
import { PartyContactDialog } from '../../../_shared/components/PartyContactDialog';

const PARTY_EDIT_PERMISSION = 'projects.parties.edit';

/**
 * The people at a party (PS-REGISTRATION-V3 rule 4): the master the register form picks a
 * project's contacts from. Phone is optional (owner 2 Nov); it can be filled at send time.
 */
export function PartyContactsPanel({ partyId }: { partyId: string }) {
  const canEdit = useHasPermission(PARTY_EDIT_PERMISSION);
  const contacts = usePartyContacts(partyId);
  const [editing, setEditing] = React.useState<PartyContact | 'new' | null>(null);
  const removal = useDeferredRowAction({
    actionKey: 'project_party_contact.delete',
    entityType: 'project_party_contact',
    verb: 'Deleting',
    successMessage: 'Contact deleted',
    // The Parties grid's Contacts count changes with it.
    invalidateKeys: [partyContactsKey(partyId), [PARTIES_KEY]],
  });

  const columns = React.useMemo<ColumnDef<PartyContact>[]>(() => {
    const text = (id: keyof PartyContact, title: string, size: number): ColumnDef<PartyContact> => ({
      id: String(id),
      accessorFn: (row) => (row[id] as string | null) ?? '',
      header: ({ column }) => <DataGridColumnHeader title={title} column={column} />,
      size,
      meta: { headerTitle: title },
      cell: ({ row }) => {
        const value = (row.original[id] as string | null) ?? '';
        return value ? (
          <span className="block truncate" title={value}>
            {value}
          </span>
        ) : (
          <span className="text-muted-foreground">-</span>
        );
      },
    });
    const cols: ColumnDef<PartyContact>[] = [
      text('name', 'Name', 200),
      text('job_title', 'Job title', 160),
      text('phone', 'Phone', 150),
      text('email', 'Email', 200),
    ];
    if (canEdit) {
      cols.push({
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 100,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label={`Edit ${row.original.name}`}
              onClick={() => setEditing(row.original)}
            >
              <Pencil className="size-4 text-muted-foreground" aria-hidden />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label={`Delete ${row.original.name}`}
              disabled={removal.targetId === row.original.id}
              onClick={() => removal.run({ id: row.original.id, subject: row.original.name })}
            >
              <Trash2 className="size-4 text-destructive" aria-hidden />
            </Button>
          </div>
        ),
      });
    }
    return cols;
  }, [canEdit, removal]);

  return (
    <>
      <PanelDataGrid<PartyContact>
        title="Contacts"
        toolbar={
          canEdit ? (
            <Button type="button" variant="outline" onClick={() => setEditing('new')}>
              <Plus className="size-4" aria-hidden />
              Add contact
            </Button>
          ) : undefined
        }
        columns={columns}
        rows={contacts.data ?? []}
        getRowId={(row) => row.id}
        listingKey={null}
        isLoading={contacts.isLoading}
        error={contacts.error}
        onRetry={() => void contacts.refetch()}
        emptyTitle="No contacts yet"
        emptyBody="The people at this firm, picked when a project is registered."
      />
      {removal.countdown}
      {editing && (
        <PartyContactDialog
          partyId={partyId}
          contact={editing === 'new' ? null : editing}
          onDone={() => setEditing(null)}
        />
      )}
    </>
  );
}
