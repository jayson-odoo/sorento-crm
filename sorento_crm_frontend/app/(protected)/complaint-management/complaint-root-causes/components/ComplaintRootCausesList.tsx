'use client';

import { useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { useComplaintRootCauses } from '../hooks/useComplaintRootCauses';
import ComplaintRootCauseTable from './ComplaintRootCauseTable';
import ComplaintRootCauseFormDialog from './ComplaintRootCauseFormDialog';
import ComplaintRootCauseDeleteDialog from './ComplaintRootCauseDeleteDialog';
import type { ComplaintRootCause } from '../types/complaintRootCause.types';

export default function ComplaintRootCausesList() {
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | undefined>(undefined);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [rowToDelete, setRowToDelete] = useState<ComplaintRootCause | null>(null);

  const { data, isLoading } = useComplaintRootCauses({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'name', desc: false }],
    searchQuery: '',
  });
  const rows = data?.data ?? [];

  const handleEdit = (row: ComplaintRootCause) => {
    setEditingId(row.id);
    setFormOpen(true);
  };

  const handleDelete = (row: ComplaintRootCause) => {
    setRowToDelete(row);
    setDeleteDialogOpen(true);
  };

  const handleFormClose = (open: boolean) => {
    setFormOpen(open);
    if (!open) setEditingId(undefined);
  };

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-2.5">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search root causes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ps-9 w-64"
            />
          </div>
          <Button
            onClick={() => {
              setEditingId(undefined);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            Add Root Cause
          </Button>
        </CardHeader>
        <CardTable>
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              Loading root causes...
            </div>
          ) : (
            <ScrollArea>
              <ComplaintRootCauseTable
                rows={rows}
                searchQuery={searchQuery}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardTable>
      </Card>

      <ComplaintRootCauseFormDialog
        open={formOpen}
        onOpenChange={handleFormClose}
        rowId={editingId}
      />

      {rowToDelete && (
        <ComplaintRootCauseDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => {
            setDeleteDialogOpen(false);
            setRowToDelete(null);
          }}
          row={rowToDelete}
        />
      )}
    </>
  );
}
