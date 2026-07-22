'use client';

import * as React from 'react';
import { useMcpAccessLog } from '../../hooks/useMcpAdmin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { StatusPill } from '@/components/common/StatusPill';

const DECISIONS = [
  { value: '__all__', label: 'All decisions' },
  { value: 'allow', label: 'Allow' },
  { value: 'deny_no_access', label: 'Deny — no access' },
  { value: 'deny_tool_unlinked', label: 'Deny — tool unlinked' },
  { value: 'deny_unknown_tool', label: 'Deny — unknown tool' },
  { value: 'deny_unknown_contact', label: 'Deny — unknown contact' },
];

const COLOR_BY_DECISION: Record<string, string> = {
  allow: '#16a34a',
  deny_no_access: '#dc2626',
  deny_tool_unlinked: '#d97706',
  deny_unknown_tool: '#6b7280',
  deny_unknown_contact: '#dc2626',
};

export function McpAccessLogList() {
  const [decision, setDecision] = React.useState<string>('__all__');
  const [toolName, setToolName] = React.useState('');
  const { data, isLoading } = useMcpAccessLog({
    decision: decision === '__all__' ? undefined : decision,
    tool_name: toolName.trim() || undefined,
  });
  const rows = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>MCP Access Log</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <SearchableSelect
            value={decision}
            onChange={setDecision}
            options={DECISIONS.map((d) => ({ value: d.value, label: d.label }))}
            triggerClassName="w-[220px]"
          />
          <Input
            placeholder="Filter by exact tool_name..."
            value={toolName}
            onChange={(e) => setToolName(e.target.value)}
            className="max-w-sm"
          />
          <span className="ml-auto text-sm text-muted-foreground">{rows.length} entries</span>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[180px]">When</TableHead>
              <TableHead className="w-[260px]">Tool</TableHead>
              <TableHead className="w-[160px]">Decision</TableHead>
              <TableHead className="w-[200px]">Contact</TableHead>
              <TableHead>Workspace</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No log entries.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{new Date(r.ts).toLocaleString()}</TableCell>
                  <TableCell className="font-mono text-xs">{r.tool_name}</TableCell>
                  <TableCell>
                    <StatusPill
                      label={r.decision}
                      colorHex={COLOR_BY_DECISION[r.decision] ?? '#6b7280'}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.contact_external_id ?? '—'}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.respond_workspace_id ?? '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
