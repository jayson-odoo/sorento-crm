'use client';

import { useMemo, useState } from 'react';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import { useChatbotDomainsQuery } from '../hooks/useChatbotDomains';
import {
  NARROWING_POLICY_OPTIONS,
  SUGGESTED_TEAM_OPTIONS,
  type ChatbotDomain,
} from '../types/chatbotDomain.types';
import ChatbotDomainModal from './ChatbotDomainModal';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

const TEAM_LABEL_BY_CODE = new Map(SUGGESTED_TEAM_OPTIONS.map((o) => [o.value, o.label]));

function narrowingSummary(domain: ChatbotDomain): string {
  const values = Object.values(domain.narrowing);
  if (values.length === 0) return 'n/a';
  const first = values[0];
  const label = NARROWING_POLICY_OPTIONS.find((o) => o.value === first)?.label ?? first;
  return label;
}

export default function ChatbotDomainsList() {
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
  } = useDebouncedSearch();
  const [supportedFilter, setSupportedFilter] = useState<'all' | 'yes' | 'no'>('all');
  const [teamFilter, setTeamFilter] = useState<string>('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Read is `system.chat_history.view` (the nav gate); writing the policy the turn
  // engine routes on is its own grant, and the backend enforces the same slug.
  const canManage = useHasPermission('system.chatbot_config.manage');
  const { data, isLoading, isError } = useChatbotDomainsQuery();
  const domains = useMemo(() => data ?? [], [data]);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return domains.filter((d) => {
      const matchesSearch =
        !q ||
        d.name.toLowerCase().includes(q) ||
        d.label.toLowerCase().includes(q) ||
        d.tools.some((t) => t.toLowerCase().includes(q)) ||
        d.switch_words.some((w) => w.toLowerCase().includes(q));
      const matchesSupported =
        supportedFilter === 'all' || (supportedFilter === 'yes' ? d.supported : !d.supported);
      const matchesTeam = !teamFilter || d.escalation_team_code === teamFilter;
      return matchesSearch && matchesSupported && matchesTeam;
    });
  }, [domains, searchQuery, supportedFilter, teamFilter]);

  const columns = useMemo<ColumnDef<ChatbotDomain>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Domain" column={column} />,
        cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
        size: 150,
        meta: { headerTitle: 'Domain' },
      },
      {
        accessorKey: 'label',
        header: ({ column }) => <DataGridColumnHeader title="Label" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.label}>
            {row.original.label}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Label' },
      },
      {
        id: 'tools',
        header: ({ column }) => <DataGridColumnHeader title="Tools" column={column} />,
        cell: ({ row }) => {
          const text = row.original.tools.join(', ') || '(none)';
          return (
            <span className="truncate block text-muted-foreground" title={text}>
              {text}
            </span>
          );
        },
        size: 240,
        meta: { headerTitle: 'Tools' },
      },
      {
        id: 'escalation_team_code',
        header: ({ column }) => <DataGridColumnHeader title="Escalation team" column={column} />,
        cell: ({ row }) => {
          const name = row.original.escalation_team_code
            ? (TEAM_LABEL_BY_CODE.get(row.original.escalation_team_code) ?? row.original.escalation_team_code)
            : '-';
          return <span className="truncate block">{name}</span>;
        },
        size: 150,
        meta: { headerTitle: 'Escalation team' },
      },
      {
        id: 'switch_words',
        header: ({ column }) => <DataGridColumnHeader title="Switch words" column={column} />,
        cell: ({ row }) => {
          const text = row.original.switch_words.join(', ') || '(none, by design)';
          return (
            <span className="truncate block text-muted-foreground" title={text}>
              {text}
            </span>
          );
        },
        size: 180,
        meta: { headerTitle: 'Switch words' },
      },
      {
        id: 'narrowing',
        header: ({ column }) => <DataGridColumnHeader title="Narrowing" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="light" size="sm">
            {narrowingSummary(row.original)}
          </Badge>
        ),
        size: 160,
        meta: { headerTitle: 'Narrowing' },
      },
      {
        accessorKey: 'takes_date_filter',
        header: ({ column }) => <DataGridColumnHeader title="Date filter" column={column} />,
        cell: ({ row }) => (row.original.takes_date_filter ? 'yes' : 'no'),
        size: 100,
        meta: { headerTitle: 'Date filter' },
      },
      {
        accessorKey: 'supported',
        header: ({ column }) => <DataGridColumnHeader title="Supported" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.supported ? 'success' : 'destructive'} appearance="light" size="sm">
            {row.original.supported ? 'on' : 'off'}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Supported' },
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.updated_at),
        size: 140,
        meta: { headerTitle: 'Updated' },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: filtered,
    columns,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  const openCreate = () => {
    setEditingId(null);
    setModalOpen(true);
  };

  const openEdit = (domain: ChatbotDomain) => {
    setEditingId(domain.id);
    setModalOpen(true);
  };

  const listPrimaryAction = canManage ? (
    <Button onClick={openCreate}>
      <Plus className="size-4" />
      Add domain
    </Button>
  ) : undefined;

  const teamActive = teamFilter !== '';
  const supportedActive = supportedFilter !== 'all';
  const filtersActive = teamActive || supportedActive;

  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Chatbot domains could not be loaded. Reload the page to try again.
      </p>
    );
  }

  return (
    <>
      <DataGrid
        table={table}
        recordCount={filtered.length}
        isLoading={isLoading}
        onRowClick={(row) => openEdit(row)}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyAction={listPrimaryAction}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  placeholder="Search domains, tools, switch words"
                  className="w-72"
                />
              }
              filters={{
                kind: 'custom',
                active: filtersActive,
                activeCount: (supportedActive ? 1 : 0) + (teamActive ? 1 : 0),
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label>Supported</Label>
                      <SearchableSelect
                        value={supportedFilter}
                        onChange={(v) => setSupportedFilter(v as 'all' | 'yes' | 'no')}
                        placeholder="All"
                        triggerClassName="mt-1"
                        options={[
                          { value: 'all', label: 'All' },
                          { value: 'yes', label: 'On' },
                          { value: 'no', label: 'Off' },
                        ]}
                      />
                    </div>
                    <div>
                      <Label>Team</Label>
                      <SearchableSelect
                        value={teamFilter}
                        onChange={setTeamFilter}
                        clearable
                        placeholder="All teams"
                        triggerClassName="mt-1"
                        options={SUGGESTED_TEAM_OPTIONS}
                      />
                    </div>
                    {filtersActive && (
                      <div className="flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setSupportedFilter('all');
                            setTeamFilter('');
                          }}
                        >
                          Clear filters
                        </Button>
                      </div>
                    )}
                  </div>
                ),
              }}
              primaryAction={listPrimaryAction}
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
        </Card>
      </DataGrid>

      <ChatbotDomainModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        domainId={editingId}
        rows={filtered}
        onNavigate={(id) => setEditingId(id)}
        canManage={canManage}
      />
    </>
  );
}
