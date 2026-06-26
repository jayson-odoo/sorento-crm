'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getExpandedRowModel,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight, Columns3, Plus, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useContactAccessAgents } from '../hooks/useContactAccessAgents';
import type { ContactAccessAgent } from '../types/contactAccessAgent.types';
import { formatDate } from '@/lib/helpers';
import ContactAgentAccessDialog from '../../access-agents/components/ContactAgentAccessDialog';
import React, { useEffect } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAccessAgents } from '../../access-agents/hooks/useAccessAgents';
import { useQueryClient } from '@tanstack/react-query';

// Grouped row type
interface ContactGroup {
  id: string;
  respond_contact_phone: string;
  respond_contact_name?: string | null;
  accessAgents: ContactAccessAgent[];
  isExpanded?: boolean;
}

export default function ContactAccessAgentsGroupedList() {
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'respond_contact_phone', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [dialogOpen, setDialogOpen] = useState(false);
  const [agentSelectDialogOpen, setAgentSelectDialogOpen] = useState(false);
  const [selectedContactPhone, setSelectedContactPhone] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [editingContactAccess, setEditingContactAccess] = useState<ContactAccessAgent | null>(null);
  
  // Fetch access agents for selection
  const { data: accessAgentsData } = useAccessAgents({
    pageIndex: 0,
    pageSize: 1000,
    sorting: [],
    searchQuery: '',
  });

  const { data, isLoading, refetch, isFetching } = useContactAccessAgents({
    pageIndex: 0,
    pageSize: 10000, // Get all for grouping
    sorting: [],
    searchQuery,
  });

  // Refresh data when dialog closes
  useEffect(() => {
    if (!dialogOpen && !agentSelectDialogOpen) {
      queryClient.invalidateQueries({ queryKey: ['contact-access-agents'] });
    }
  }, [dialogOpen, agentSelectDialogOpen, queryClient]);

  // Group data by contact phone
  const groupedData = useMemo(() => {
    if (!data?.data) return [];

    const groupsMap = new Map<string, ContactGroup>();

    data.data.forEach((item) => {
      const phone = item.respond_contact_phone;
      if (!groupsMap.has(phone)) {
        groupsMap.set(phone, {
          id: `group-${phone}`,
          respond_contact_phone: phone,
          respond_contact_name: item.respond_contact_name,
          accessAgents: [],
          isExpanded: expandedGroups.has(phone),
        });
      }
      groupsMap.get(phone)!.accessAgents.push(item);
    });

    return Array.from(groupsMap.values()).sort((a, b) => {
      if (sorting[0]?.id === 'respond_contact_phone') {
        return sorting[0]?.desc
          ? b.respond_contact_phone.localeCompare(a.respond_contact_phone)
          : a.respond_contact_phone.localeCompare(b.respond_contact_phone);
      }
      return 0;
    });
  }, [data?.data, expandedGroups, sorting]);

  const toggleGroup = (phone: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(phone)) {
        next.delete(phone);
      } else {
        next.add(phone);
      }
      return next;
    });
  };

  const handleAddAccessAgent = (contactPhone: string) => {
    setSelectedContactPhone(contactPhone);
    setEditingContactAccess(null);
    setSelectedAgentId('');
    setAgentSelectDialogOpen(true);
  };

  const handleAgentSelected = () => {
    if (selectedAgentId) {
      setAgentSelectDialogOpen(false);
      setDialogOpen(true);
    }
  };

  const handleEditAccessAgent = (contactAccess: ContactAccessAgent) => {
    setSelectedContactPhone(contactAccess.respond_contact_phone);
    setEditingContactAccess(contactAccess);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setSelectedContactPhone(null);
    setEditingContactAccess(null);
    setSelectedAgentId('');
    // Invalidate queries to refresh the list
    queryClient.invalidateQueries({ queryKey: ['contact-access-agents'] });
  };

  const columns = useMemo<ColumnDef<ContactGroup>[]>(
    () => [
      {
        id: 'expand',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => toggleGroup(row.original.respond_contact_phone)}
          >
            {expandedGroups.has(row.original.respond_contact_phone) ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </Button>
        ),
        size: 50,
      },
      {
        accessorKey: 'respond_contact_phone',
        header: ({ column }) => <DataGridColumnHeader title="Respond Contact Phone" column={column} />,
        size: 200,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <span className="font-medium">{row.original.respond_contact_phone}</span>
            <Badge variant="secondary" size="sm">
              {row.original.accessAgents.length} agent{row.original.accessAgents.length !== 1 ? 's' : ''}
            </Badge>
          </div>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'respond_contact_name',
        header: ({ column }) => <DataGridColumnHeader title="Respond Contact Name" column={column} />,
        size: 220,
        cell: ({ row }) => row.original.respond_contact_name || '-',
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleAddAccessAgent(row.original.respond_contact_phone)}
          >
            <Plus className="size-4 mr-1" />
            Add Agent
          </Button>
        ),
        size: 120,
      },
    ],
    [expandedGroups],
  );

  const table = useReactTable({
    columns,
    data: groupedData,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    manualPagination: true,
    manualSorting: true,
  });

  return (
    <>
      <DataGrid
        table={table}
        tableLayout={{ columnsVisibility: true }}
        recordCount={groupedData.length}
        isLoading={isLoading}
        onRefresh={() => void refetch()}
        isRefreshing={isFetching && !isLoading}
      >
        <Card>
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search contact access agents..."
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
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b">
                    {table.getHeaderGroups()[0]?.headers.map((header) => (
                      <th
                        key={header.id}
                        className="text-left p-4 font-medium text-sm text-muted-foreground"
                        style={{ width: header.getSize() }}
                      >
                        {header.isPlaceholder
                          ? null
                          : header.column.columnDef.header
                            ? typeof header.column.columnDef.header === 'function'
                              ? header.column.columnDef.header(header.getContext())
                              : header.column.columnDef.header
                            : null}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td colSpan={columns.length} className="p-4">
                        <div className="text-center text-muted-foreground">Loading...</div>
                      </td>
                    </tr>
                  ) : groupedData.length === 0 ? (
                    <tr>
                      <td colSpan={columns.length} className="p-4">
                        <div className="text-center text-muted-foreground">No contact access agents found</div>
                      </td>
                    </tr>
                  ) : (
                    groupedData.map((group) => (
                      <React.Fragment key={group.id}>
                        <tr className="border-b hover:bg-accent/50">
                          {table.getHeaderGroups()[0]?.headers.map((header) => {
                            const cell = table.getRow(group.id)?.getVisibleCells().find((c) => c.column.id === header.id);
                            return (
                              <td key={header.id} className="p-4" style={{ width: header.getSize() }}>
                                {cell ? (
                                  typeof cell.column.columnDef.cell === 'function'
                                    ? cell.column.columnDef.cell(cell.getContext())
                                    : cell.column.columnDef.cell
                                ) : null}
                              </td>
                            );
                          })}
                        </tr>
                        {expandedGroups.has(group.respond_contact_phone) && (
                          <tr>
                            <td colSpan={columns.length} className="p-0 bg-muted/30">
                              <div className="p-4">
                                <div className="mb-3 font-medium text-sm">Access Agents for {group.respond_contact_phone}</div>
                                <table className="w-full border-collapse">
                                  <thead>
                                    <tr className="border-b">
                                      <th className="text-left p-2 text-xs font-medium text-muted-foreground">Agent Code</th>
                                      <th className="text-left p-2 text-xs font-medium text-muted-foreground">Agent Name</th>
                                      <th className="text-left p-2 text-xs font-medium text-muted-foreground">Allowed</th>
                                      <th className="text-left p-2 text-xs font-medium text-muted-foreground">Valid From</th>
                                      <th className="text-left p-2 text-xs font-medium text-muted-foreground">Valid To</th>
                                      <th className="text-left p-2 text-xs font-medium text-muted-foreground">Created At</th>
                                      <th className="text-left p-2 text-xs font-medium text-muted-foreground">Actions</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {group.accessAgents.map((agent) => (
                                      <tr key={agent.id} className="border-b hover:bg-background">
                                        <td className="p-2 text-sm">{agent.agent_code || '-'}</td>
                                        <td className="p-2 text-sm">{agent.agent_name || '-'}</td>
                                        <td className="p-2">
                                          <Badge variant={agent.is_allowed ? 'success' : 'secondary'} appearance="ghost" size="sm">
                                            {agent.is_allowed ? 'Yes' : 'No'}
                                          </Badge>
                                        </td>
                                        <td className="p-2 text-sm">{agent.valid_from ? formatDate(new Date(agent.valid_from)) : '-'}</td>
                                        <td className="p-2 text-sm">{agent.valid_to ? formatDate(new Date(agent.valid_to)) : '-'}</td>
                                        <td className="p-2 text-sm">{formatDate(new Date(agent.created_at))}</td>
                                        <td className="p-2">
                                          <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => handleEditAccessAgent(agent)}
                                          >
                                            Edit
                                          </Button>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))
                  )}
                </tbody>
              </table>
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          <CardFooter>
            <div className="text-sm text-muted-foreground">
              Showing {groupedData.length} contact{groupedData.length !== 1 ? 's' : ''}
            </div>
          </CardFooter>
        </Card>
      </DataGrid>

      {/* Agent Selection Dialog */}
      <Dialog open={agentSelectDialogOpen} onOpenChange={setAgentSelectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Select Access Agent</DialogTitle>
            <DialogDescription>
              Choose an access agent to add for contact {selectedContactPhone}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
              <SelectTrigger>
                <SelectValue placeholder="Select access agent" />
              </SelectTrigger>
              <SelectContent>
                {(accessAgentsData?.data || [])
                  .filter((agent) => agent.is_active)
                  .map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name} ({agent.code})
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAgentSelectDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAgentSelected} disabled={!selectedAgentId}>
              Continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add/Edit Dialog */}
      {selectedContactPhone && selectedAgentId && (
        <ContactAgentAccessDialog
          open={dialogOpen}
          onOpenChange={(open) => {
            if (!open) {
              handleDialogClose();
            } else {
              setDialogOpen(open);
            }
          }}
          accessAgentId={editingContactAccess?.agent_id || selectedAgentId}
          contactAccess={editingContactAccess}
          defaultContactPhone={selectedContactPhone}
        />
      )}
    </>
  );
}
