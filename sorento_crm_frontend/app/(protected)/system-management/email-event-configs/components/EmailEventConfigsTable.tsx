'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  useEmailEventConfigs,
  useUpdateEmailEventConfig,
} from '../hooks/useEmailEventConfigs';
import type { EmailEventConfig } from '../types/emailEventConfig.types';

interface OverrideDraft {
  rate_per_window_override: string;
  window_seconds_override: string;
  coalesce_window_seconds_override: string;
}

function _toIntOrNull(value: string): number | null | undefined {
  if (value === '') return null;
  const n = Number(value);
  if (Number.isNaN(n)) return undefined;
  return n;
}

export default function EmailEventConfigsTable() {
  const { data, isLoading } = useEmailEventConfigs();
  const updateMut = useUpdateEmailEventConfig();
  const [drafts, setDrafts] = useState<Record<string, OverrideDraft>>({});

  function getDraft(row: EmailEventConfig): OverrideDraft {
    return (
      drafts[row.event_key] ?? {
        rate_per_window_override: row.rate_per_window_override?.toString() ?? '',
        window_seconds_override: row.window_seconds_override?.toString() ?? '',
        coalesce_window_seconds_override:
          row.coalesce_window_seconds_override?.toString() ?? '',
      }
    );
  }

  function setDraftField(event_key: string, field: keyof OverrideDraft, value: string) {
    setDrafts((d) => ({
      ...d,
      [event_key]: { ...getDraft({ event_key } as EmailEventConfig), ...d[event_key], [field]: value },
    }));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email event kill switches</CardTitle>
        <CardDescription>
          One row per email event. Disable an event to silence it without redeploy. Override rate
          caps or coalesce windows per event when defaults are too tight or too loose.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <div className="overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[260px]">Event</TableHead>
                  <TableHead className="w-[110px]">Enabled</TableHead>
                  <TableHead className="w-[150px]">Rate / window override</TableHead>
                  <TableHead className="w-[150px]">Window seconds override</TableHead>
                  <TableHead className="w-[170px]">Coalesce seconds override</TableHead>
                  <TableHead className="w-[120px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data ?? []).map((row) => {
                  const draft = getDraft(row);
                  return (
                    <TableRow key={row.event_key}>
                      <TableCell>
                        <div className="font-medium">{row.display_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">{row.event_key}</div>
                        {row.description && (
                          <div className="text-xs text-muted-foreground mt-1 max-w-[480px]">
                            {row.description}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Switch
                          checked={row.enabled}
                          onCheckedChange={(checked) =>
                            updateMut.mutate({
                              event_key: row.event_key,
                              payload: { enabled: checked },
                            })
                          }
                          disabled={updateMut.isPending}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          placeholder="default"
                          value={draft.rate_per_window_override}
                          onChange={(e) =>
                            setDraftField(row.event_key, 'rate_per_window_override', e.target.value)
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          placeholder="default"
                          value={draft.window_seconds_override}
                          onChange={(e) =>
                            setDraftField(row.event_key, 'window_seconds_override', e.target.value)
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          placeholder="default"
                          value={draft.coalesce_window_seconds_override}
                          onChange={(e) =>
                            setDraftField(
                              row.event_key,
                              'coalesce_window_seconds_override',
                              e.target.value,
                            )
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={updateMut.isPending}
                          onClick={() => {
                            const r = _toIntOrNull(draft.rate_per_window_override);
                            const w = _toIntOrNull(draft.window_seconds_override);
                            const c = _toIntOrNull(draft.coalesce_window_seconds_override);
                            updateMut.mutate({
                              event_key: row.event_key,
                              payload: {
                                rate_per_window_override: r ?? null,
                                window_seconds_override: w ?? null,
                                coalesce_window_seconds_override: c ?? null,
                              },
                            });
                          }}
                        >
                          Save overrides
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
