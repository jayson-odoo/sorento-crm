'use client';

import { useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { useComplaintResolutions } from '../hooks/useComplaintResolutions';
import ComplaintResolutionTable from './ComplaintResolutionTable';
import ComplaintResolutionFormDialog from './ComplaintResolutionFormDialog';
import ComplaintResolutionDeleteDialog from './ComplaintResolutionDeleteDialog';
import type { ComplaintResolution } from '../types/complaintResolution.types';

export default function ComplaintResolutionsList() {
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | undefined>(undefined);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [rowToDelete, setRowToDelete] = useState<ComplaintResolution | null>(null);

  const { data, isLoading } = useComplaintResolutions({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'name', desc: false }],
    searchQuery: '',
  });
  const rows = data?.data ?? [];

  const handleEdit = (row: ComplaintResolution) => {
    setEditingId(row.id);
    setFormOpen(true);
  };

  const handleDelete = (row: ComplaintResolution) => {
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
              placeholder="Search resolutions..."
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
            Add Resolution
          </Button>
        </CardHeader>
        <CardTable>
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              Loading resolutions...
            </div>
          ) : (
            <ScrollArea>
              <ComplaintResolutionTable
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

      <ComplaintResolutionFormDialog
        open={formOpen}
        onOpenChange={handleFormClose}
        rowId={editingId}
      />

      {rowToDelete && (
        <ComplaintResolutionDeleteDialog
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
