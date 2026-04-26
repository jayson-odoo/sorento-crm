'use client';

import { type ReactNode, useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useCreateCommercialProject, useProjectTaskTemplates } from '../hooks/useCommercialProjects';
import type { CommercialProjectDetail } from '../types/commercialProject.types';
import { useCustomerSelectQuery } from '@/app/(protected)/order-management/shared/hooks/use-customer-select-query';
import { SearchableSelect } from '@/components/common/SearchableSelect';

/** Required field shell — red indicator only while value is missing. */
function RequiredFieldShell({
  className,
  children,
  missing = false,
}: {
  className?: string;
  children: ReactNode;
  missing?: boolean;
}) {
  return (
    <div
      className={cn(
        'min-w-0 overflow-hidden rounded-[4px] border border-[#d1d5dc] bg-background shadow-xs',
        missing && 'border-l-4 border-l-[#fb2c36]',
        '[&_[data-slot=select-trigger]]:h-10 [&_[data-slot=select-trigger]]:rounded-none [&_[data-slot=select-trigger]]:border-0 [&_[data-slot=select-trigger]]:shadow-none',
        '[&_input]:h-10 [&_input]:rounded-none [&_input]:border-0 [&_input]:shadow-none [&_input]:bg-transparent',
        '[&_textarea]:rounded-none [&_textarea]:border-0 [&_textarea]:shadow-none [&_textarea]:bg-transparent',
        className,
      )}
    >
      {children}
    </div>
  );
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional: link the new project to a lead at creation time. */
  defaultLeadId?: string | null;
  /** Called after successful create (e.g. navigate to the new project) */
  onProjectCreated?: (project: CommercialProjectDetail) => void;
};

export default function CreateProjectDialog({
  open,
  onOpenChange,
  defaultLeadId = null,
  onProjectCreated,
}: Props) {
  const [title, setTitle] = useState('');
  const [brief, setBrief] = useState('');
  const [notes, setNotes] = useState('');
  const [addressLine1, setAddressLine1] = useState('');
  const [addressLine2, setAddressLine2] = useState('');
  const [postcode, setPostcode] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [country, setCountry] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [taskTemplateId, setTaskTemplateId] = useState('');
  const [developerCustomerId, setDeveloperCustomerId] = useState('');
  const createMut = useCreateCommercialProject();
  const { data: templates = [], isLoading: loadingTemplates } = useProjectTaskTemplates();
  const { data: customerOptions = [], isLoading: loadingCustomers } = useCustomerSelectQuery({ enabled: open });

  useEffect(() => {
    if (!open) {
      setTitle('');
      setBrief('');
      setNotes('');
      setAddressLine1('');
      setAddressLine2('');
      setPostcode('');
      setCity('');
      setState('');
      setCountry('');
      setStartDate('');
      setEndDate('');
      setTaskTemplateId('');
      setDeveloperCustomerId('');
    }
  }, [open]);

  const submit = () => {
    const missing: string[] = [];
    if (!title.trim()) missing.push('Project title');
    if (!developerCustomerId.trim()) missing.push('Developer');
    if (missing.length) {
      toast.error(
        missing.length === 1
          ? `${missing[0]} is required.`
          : `Required: ${missing.join(', ')}.`,
      );
      return;
    }
    createMut.mutate(
      {
        lead_id: defaultLeadId || null,
        title: title.trim(),
        brief: brief.trim() || null,
        notes: notes.trim() || null,
        address_line_1: addressLine1.trim() || null,
        address_line_2: addressLine2.trim() || null,
        postcode: postcode.trim() || null,
        city: city.trim() || null,
        state: state.trim() || null,
        country: country.trim() || null,
        start_date: startDate || null,
        end_date: endDate || null,
        task_template_id: taskTemplateId || null,
        developer_customer_id: developerCustomerId,
      },
      {
        onSuccess: (project) => {
          onOpenChange(false);
          onProjectCreated?.(project);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] flex flex-col gap-0 p-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b">
          <DialogTitle>New project</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 px-6 py-4 overflow-y-auto flex-1 min-h-0">
          <div className="grid gap-2">
            <Label htmlFor="cp-title">Project title</Label>
            <RequiredFieldShell missing={!title.trim()}>
              <Textarea
                id="cp-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                rows={3}
                className="resize-y min-h-[72px]"
              />
            </RequiredFieldShell>
          </div>
          <div className="grid gap-2">
            <Label>Developer</Label>
            <RequiredFieldShell missing={!developerCustomerId.trim()}>
              <SearchableSelect
                value={developerCustomerId}
                onChange={setDeveloperCustomerId}
                disabled={loadingCustomers}
                placeholder={loadingCustomers ? 'Loading…' : 'Select developer'}
                triggerClassName="border-0 shadow-none focus-visible:ring-0"
                options={customerOptions.map((c) => ({
                  value: c.id,
                  label: `${c.customer_code} — ${c.customer_name}`,
                  searchText: `${c.customer_code} ${c.customer_name}`,
                }))}
              />
            </RequiredFieldShell>
          </div>
          <div className="grid gap-2">
            <Label>Brief</Label>
            <Input value={brief} onChange={(e) => setBrief(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Notes</Label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </div>
          <div className="grid gap-2">
            <Label>Address line 1</Label>
            <Input value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Address line 2</Label>
            <Input value={addressLine2} onChange={(e) => setAddressLine2(e.target.value)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>Postcode</Label>
              <Input value={postcode} onChange={(e) => setPostcode(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>City</Label>
              <Input value={city} onChange={(e) => setCity(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>State</Label>
              <Input value={state} onChange={(e) => setState(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>Country</Label>
              <Input value={country} onChange={(e) => setCountry(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>Start date</Label>
              <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>End date</Label>
              <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Task template</Label>
            <Select
              value={taskTemplateId || '__none__'}
              onValueChange={(v) => setTaskTemplateId(v === '__none__' ? '' : v)}
              disabled={loadingTemplates}
            >
              <SelectTrigger>
                <SelectValue placeholder={loadingTemplates ? 'Loading…' : 'Optional'} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">None</SelectItem>
                {templates.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter className="px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={submit} disabled={createMut.isPending}>
            Create project
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
