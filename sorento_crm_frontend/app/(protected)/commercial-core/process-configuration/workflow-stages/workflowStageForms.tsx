'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import type {
  WorkflowDomain,
  WorkflowStageCreatePayload,
  WorkflowStageRow,
  WorkflowStageUpdatePayload,
} from '../types/workflowStage.types';

export const ADMIN_DOMAINS: { value: WorkflowDomain; label: string }[] = [
  { value: 'lead', label: 'Lead' },
  { value: 'quotation', label: 'Quotation' },
  { value: 'tender', label: 'Tender' },
  { value: 'task', label: 'Task' },
  { value: 'order', label: 'Order' },
  { value: 'project', label: 'Project' },
];

export function EditStageForm({
  row,
  submitting,
  onSubmit,
}: {
  row: WorkflowStageRow;
  submitting: boolean;
  onSubmit: (data: WorkflowStageUpdatePayload) => void;
}) {
  const [label, setLabel] = useState(row.label);
  const [colorHex, setColorHex] = useState(row.color_hex || '#E7000B');
  const [sortOrder, setSortOrder] = useState(String(row.sort_order));
  const [isTerminal, setIsTerminal] = useState(row.is_terminal);
  const [allowsConversion, setAllowsConversion] = useState<boolean | null>(row.allows_conversion);
  const [canGoBack, setCanGoBack] = useState(row.can_go_back);
  const [isActive, setIsActive] = useState(row.is_active);
  const [isCancelled, setIsCancelled] = useState(row.is_cancelled);

  return (
    <>
      <div className="grid gap-4 py-2">
        <div className="text-muted-foreground text-sm">
          {row.domain} / {row.code}
        </div>
        <div className="space-y-2">
          <Label htmlFor="ws-label">Label</Label>
          <Input id="ws-label" value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ws-color">Color</Label>
          <div className="flex items-center gap-2">
            <Input id="ws-color" type="color" value={colorHex} onChange={(e) => setColorHex(e.target.value)} className="h-10 w-14 p-1" />
            <Input value={colorHex} onChange={(e) => setColorHex(e.target.value)} placeholder="#E7000B" />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="ws-order">Sort order</Label>
          <Input id="ws-order" type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="ws-term">Terminal</Label>
          <Switch id="ws-term" checked={isTerminal} onCheckedChange={setIsTerminal} />
        </div>
        {row.domain === 'lead' ? (
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="ws-conv">Allows conversion</Label>
            <Switch
              id="ws-conv"
              checked={allowsConversion === true}
              onCheckedChange={(c) => setAllowsConversion(c ? true : false)}
            />
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="ws-back">Can go back</Label>
          <Switch id="ws-back" checked={canGoBack} onCheckedChange={setCanGoBack} />
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="ws-active">Active</Label>
          <Switch id="ws-active" checked={isActive} onCheckedChange={setIsActive} />
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="ws-can">Cancelled (lost)</Label>
          <Switch id="ws-can" checked={isCancelled} onCheckedChange={setIsCancelled} />
        </div>
      </div>
      <DialogFooter>
        <Button
          type="button"
          disabled={submitting}
          onClick={() => {
            const base: WorkflowStageUpdatePayload = {
              label: label.trim(),
              color_hex: colorHex.trim() || null,
              sort_order: parseInt(sortOrder, 10) || 0,
              is_terminal: isTerminal,
              can_go_back: canGoBack,
              is_active: isActive,
              is_cancelled: isCancelled,
            };
            if (row.domain === 'lead') base.allows_conversion = allowsConversion;
            onSubmit(base);
          }}
        >
          Save
        </Button>
      </DialogFooter>
    </>
  );
}

export function CreateStageForm({
  submitting,
  onSubmit,
  lockDomain,
}: {
  submitting: boolean;
  onSubmit: (data: WorkflowStageCreatePayload) => void;
  lockDomain?: WorkflowDomain;
}) {
  const [domain, setDomain] = useState<WorkflowDomain>(lockDomain ?? 'lead');
  const [code, setCode] = useState('');
  const [label, setLabel] = useState('');
  const [colorHex, setColorHex] = useState('#E7000B');
  const [sortOrder, setSortOrder] = useState('0');
  const [isTerminal, setIsTerminal] = useState(false);
  const [allowsConversion, setAllowsConversion] = useState(false);
  const [canGoBack, setCanGoBack] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [isCancelled, setIsCancelled] = useState(false);

  useEffect(() => {
    if (lockDomain) setDomain(lockDomain);
  }, [lockDomain]);

  const effectiveDomain = lockDomain ?? domain;

  return (
    <>
      <div className="grid gap-4 py-2">
        {lockDomain ? (
          <div className="text-muted-foreground text-sm capitalize">Domain: {lockDomain}</div>
        ) : (
          <div className="space-y-2">
            <Label>Domain</Label>
            <Select value={domain} onValueChange={(v) => setDomain(v as WorkflowDomain)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ADMIN_DOMAINS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="space-y-2">
          <Label htmlFor="n-code">Code</Label>
          <Input id="n-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. qualified" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="n-label">Label</Label>
          <Input id="n-label" value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="n-color">Color</Label>
          <div className="flex items-center gap-2">
            <Input id="n-color" type="color" value={colorHex} onChange={(e) => setColorHex(e.target.value)} className="h-10 w-14 p-1" />
            <Input value={colorHex} onChange={(e) => setColorHex(e.target.value)} placeholder="#E7000B" />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="n-order">Sort order</Label>
          <Input id="n-order" type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label>Terminal</Label>
          <Switch checked={isTerminal} onCheckedChange={setIsTerminal} />
        </div>
        {effectiveDomain === 'lead' ? (
          <div className="flex items-center justify-between gap-4">
            <Label>Allows conversion</Label>
            <Switch checked={allowsConversion} onCheckedChange={setAllowsConversion} />
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-4">
          <Label>Can go back</Label>
          <Switch checked={canGoBack} onCheckedChange={setCanGoBack} />
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label>Active</Label>
          <Switch checked={isActive} onCheckedChange={setIsActive} />
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label>Cancelled</Label>
          <Switch checked={isCancelled} onCheckedChange={setIsCancelled} />
        </div>
      </div>
      <DialogFooter>
        <Button
          type="button"
          disabled={submitting || !code.trim() || !label.trim()}
          onClick={() =>
            onSubmit({
              domain: effectiveDomain,
              code: code.trim(),
              label: label.trim(),
              color_hex: colorHex.trim() || null,
              description: null,
              sort_order: parseInt(sortOrder, 10) || 0,
              is_terminal: isTerminal,
              allows_conversion: effectiveDomain === 'lead' ? allowsConversion : null,
              can_go_back: canGoBack,
              is_active: isActive,
              is_cancelled: isCancelled,
            })
          }
        >
          Create
        </Button>
      </DialogFooter>
    </>
  );
}
