'use client';

import * as React from 'react';
import { useMcpToolsCatalog } from '../hooks/useMcpAdmin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

export function McpToolsList() {
  const [includeInactive, setIncludeInactive] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const { data, isLoading } = useMcpToolsCatalog({ is_active: !includeInactive });
  const rows = (data ?? []).filter((r) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      r.tool_name.toLowerCase().includes(q) ||
      r.module_key.toLowerCase().includes(q)
    );
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>MCP Tools Catalog</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-4">
          <Input
            placeholder="Search tool / module / owner..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-sm"
          />
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={includeInactive} onCheckedChange={(v) => setIncludeInactive(v)} />
            Show deactivated
          </label>
          <span className="ml-auto text-sm text-muted-foreground">{rows.length} tools</span>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[280px]">Tool</TableHead>
              <TableHead className="w-[140px]">Module</TableHead>
              <TableHead>Description</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  No tools match.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.tool_name}</TableCell>
                  <TableCell>{r.module_key || '—'}</TableCell>
                  <TableCell className="truncate" title={r.description ?? ''}>
                    {r.description ?? '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        <p className="text-xs text-muted-foreground">
          To assign a tool to an access agent, edit the agent under{' '}
          <code className="font-mono">User Management → Access Agents</code> and select tools in
          the &quot;MCP Tools&quot; card.
        </p>
      </CardContent>
    </Card>
  );
}
