'use client';

import { useMemo, useState } from 'react';
import { useSession } from 'next-auth/react';
import {
  RowSelectionState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { isSuperadminUser } from '@/lib/is-superadmin';
import { useCompanies } from '../hooks/useCompanies';
import { buildCompanyColumns } from './CompanyTable';
import CompanyFormDialog from './CompanyFormDialog';
import CompanyDeleteDialog from './CompanyDeleteDialog';
import CompanyAccessDialog from './CompanyAccessDialog';
import type { Company } from '../types/company.types';

export default function CompaniesList() {
  // Companies admin is superadmin/admin-only (backend enforces via role slug;
  // this is the UX guard for direct navigation). TODO(AC-A1/A4): swap for a
  // `system.companies.manage` permission slug once the backend defines one.
  const { data: session, status } = useSession();
  const denied = status === 'authenticated' && !isSuperadminUser(session?.user);

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [formOpen, setFormOpen] = useState(false);
  const [editingCompanyId, setEditingCompanyId] = useState<string | undefined>(undefined);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [companyToDelete, setCompanyToDelete] = useState<Company | null>(null);
  const [accessCompany, setAccessCompany] = useState<Company | null>(null);

  const { data, isLoading } = useCompanies({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'name', desc: false }],
    searchQuery: '',
  });

  const handleEdit = (company: Company) => {
    setEditingCompanyId(company.id);
    setFormOpen(true);
  };

  const handleManageAccess = (company: Company) => {
    setAccessCompany(company);
  };

  const handleDelete = (company: Company) => {
    setCompanyToDelete(company);
    setDeleteDialogOpen(true);
  };

  const handleFormClose = (open: boolean) => {
    setFormOpen(open);
    if (!open) setEditingCompanyId(undefined);
  };

  // Search + status are filtered client-side (the list loads up to 100 companies).
  const filteredCompanies = useMemo(() => {
    const companies = data?.data ?? [];
    const q = searchQuery.toLowerCase();
    return companies.filter((c) => {
      const matchesSearch =
        !q || c.name?.toLowerCase().includes(q) || c.code?.toLowerCase().includes(q);
      const matchesStatus =
        statusFilter === 'all' || (statusFilter === 'active' ? c.is_active : !c.is_active);
      return matchesSearch && matchesStatus;
    });
  }, [data, searchQuery, statusFilter]);

  const columns = useMemo(
    () =>
      buildCompanyColumns({
        onEdit: handleEdit,
        onManageAccess: handleManageAccess,
        onDelete: handleDelete,
      }),
    [],
  );

  const table = useReactTable({
    columns,
    data: filteredCompanies,
    getRowId: (row) => row.id,
    state: { rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
  });

  const statusActive = statusFilter !== 'all';

  if (denied) {
    return (
      <div className="rounded-md border p-6 text-sm text-muted-foreground">
        Forbidden — you don&apos;t have permission to manage companies.
      </div>
    );
  }

  return (
    <>
      <DataGrid
        table={table}
        recordCount={filteredCompanies.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search companies..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="ps-9 w-64"
                  />
                  {searchQuery && (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                      onClick={() => setSearchQuery('')}
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              filters={{
                kind: 'custom',
                active: statusActive,
                activeCount: statusActive ? 1 : 0,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label>Status</Label>
                      <SearchableSelect
                        value={statusFilter}
                        onChange={(v) => setStatusFilter(v as 'all' | 'active' | 'inactive')}
                        placeholder="All statuses"
                        triggerClassName="mt-1"
                        options={[
                          { value: 'all', label: 'All statuses' },
                          { value: 'active', label: 'Active' },
                          { value: 'inactive', label: 'Inactive' },
                        ]}
                      />
                    </div>
                    {statusActive && (
                      <div className="flex justify-end">
                        <Button variant="ghost" size="sm" onClick={() => setStatusFilter('all')}>
                          Clear filters
                        </Button>
                      </div>
                    )}
                  </div>
                ),
              }}
              exportConfig={{ filename: 'companies_export.xlsx' }}
              primaryAction={
                <Button
                  onClick={() => {
                    setEditingCompanyId(undefined);
                    setFormOpen(true);
                  }}
                >
                  <Plus className="size-4" />
                  Create Company
                </Button>
              }
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      </DataGrid>

      <CompanyFormDialog
        open={formOpen}
        onOpenChange={handleFormClose}
        companyId={editingCompanyId}
      />

      {accessCompany && (
        <CompanyAccessDialog
          open={!!accessCompany}
          onOpenChange={(open) => {
            if (!open) setAccessCompany(null);
          }}
          company={accessCompany}
        />
      )}

      {companyToDelete && (
        <CompanyDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => {
            setDeleteDialogOpen(false);
            setCompanyToDelete(null);
          }}
          company={companyToDelete}
        />
      )}
    </>
  );
}
