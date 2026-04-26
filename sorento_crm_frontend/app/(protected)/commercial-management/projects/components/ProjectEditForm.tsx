'use client';

import { type ReactNode, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useCommercialProject, useUpdateCommercialProject } from '../hooks/useCommercialProjects';
import { formatProjectDisplayCode, projectStageHeaderClass } from '../utils/projectDisplay';
import { useCustomerSelectQuery } from '@/app/(protected)/order-management/shared/hooks/use-customer-select-query';
import { SearchableSelect } from '@/components/common/SearchableSelect';

/** Bordered shell aligned with Lead edit — red accent only while required value is missing. */
function FieldShell({
  missing,
  className,
  children,
}: {
  missing?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        'min-w-0 overflow-hidden rounded-[4px] border border-[#d1d5dc] bg-background shadow-xs',
        '[&_[data-slot=select-trigger]]:h-10 [&_[data-slot=select-trigger]]:rounded-none [&_[data-slot=select-trigger]]:border-0 [&_[data-slot=select-trigger]]:shadow-none',
        '[&_input]:h-10 [&_input]:rounded-none [&_input]:border-0 [&_input]:shadow-none [&_input]:bg-transparent',
        '[&_textarea]:min-h-[88px] [&_textarea]:rounded-none [&_textarea]:border-0 [&_textarea]:shadow-none [&_textarea]:bg-transparent',
        missing && 'border-l-4 border-l-[#fb2c36]',
        className,
      )}
    >
      {children}
    </div>
  );
}

export default function ProjectEditForm({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { data: project, isLoading } = useCommercialProject(projectId);
  const updateMut = useUpdateCommercialProject(projectId);
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
  const [developerCustomerId, setDeveloperCustomerId] = useState('');

  const { data: workflowProjectStages = [] } = useQuery({
    queryKey: ['workflow-stages', 'project'],
    queryFn: () => getWorkflowStages({ domain: 'project' }),
    staleTime: 60_000,
  });
  const { data: customerOptions = [], isLoading: loadingCustomers } = useCustomerSelectQuery();

  useEffect(() => {
    if (!project) return;
    setTitle(project.title ?? '');
    setBrief(project.brief ?? '');
    setNotes(project.notes ?? '');
    setAddressLine1(project.address_line_1 ?? '');
    setAddressLine2(project.address_line_2 ?? '');
    setPostcode(project.postcode ?? '');
    setCity(project.city ?? '');
    setState(project.state ?? '');
    setCountry(project.country ?? '');
    setStartDate(project.start_date?.slice(0, 10) ?? '');
    setEndDate(project.end_date?.slice(0, 10) ?? '');
    setDeveloperCustomerId(project.developer_customer_id ?? '');
  }, [project?.updated_at, project?.lead_id]);

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
    updateMut.mutate(
      {
        title: title.trim() || null,
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
        developer_customer_id: developerCustomerId,
      },
      {
        onSuccess: () => router.push(`/commercial-management/projects/${projectId}`),
      },
    );
  };

  if (isLoading || !project) {
    return (
      <div className="w-full space-y-4 px-6 py-6">
        <Skeleton className="h-10 w-full max-w-xl" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  const stageMeta = workflowProjectStages.find((s) => s.id === project.project_stage_id);

  return (
    <div className="w-full space-y-8 px-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight text-[#101828]">Edit project</h1>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="secondary"
              className={cn(
                'font-medium normal-case',
                projectStageHeaderClass(stageMeta?.code ?? project.project_stage_code ?? project.status),
              )}
            >
              {stageMeta?.label ?? project.project_stage_name ?? project.status}
            </Badge>
            <span className="font-mono text-sm text-[#6a7282]">{formatProjectDisplayCode(projectId)}</span>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button type="button" variant="outline" className="rounded-[10px]" asChild>
            <Link href={`/commercial-management/projects/${projectId}`}>Cancel</Link>
          </Button>
          <Button
            type="button"
            className="rounded-[10px] bg-[#e7000b] hover:bg-[#e7000b]/90"
            onClick={submit}
            disabled={updateMut.isPending}
          >
            Save changes
          </Button>
        </div>
      </div>

      <Card className="rounded-[10px] border border-[#e5e7eb] shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold">Basic information</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-2">
            <Label className="text-sm font-medium text-[#4a5565]">Project code</Label>
            <FieldShell className="[&_input]:bg-muted/40">
              <Input
                readOnly
                tabIndex={-1}
                variant="lg"
                className="cursor-default text-muted-foreground"
                value={formatProjectDisplayCode(projectId)}
              />
            </FieldShell>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pe-title" className="text-sm font-medium text-[#4a5565]">
              Project title
            </Label>
            <FieldShell missing={!title.trim()}>
              <Textarea
                id="pe-title"
                rows={3}
                variant="lg"
                className="resize-y"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </FieldShell>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pe-brief" className="text-sm font-medium text-[#4a5565]">
              Project brief
            </Label>
            <FieldShell>
              <Textarea id="pe-brief" rows={3} variant="lg" value={brief} onChange={(e) => setBrief(e.target.value)} />
            </FieldShell>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="pe-start" className="text-sm font-medium text-[#4a5565]">
                Start date
              </Label>
              <FieldShell>
                <Input id="pe-start" type="date" variant="lg" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </FieldShell>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pe-end" className="text-sm font-medium text-[#4a5565]">
                End date
              </Label>
              <FieldShell>
                <Input id="pe-end" type="date" variant="lg" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </FieldShell>
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pe-address1" className="text-sm font-medium text-[#4a5565]">
              Address line 1
            </Label>
            <FieldShell>
              <Input id="pe-address1" variant="lg" value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} />
            </FieldShell>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pe-address2" className="text-sm font-medium text-[#4a5565]">
              Address line 2
            </Label>
            <FieldShell>
              <Input id="pe-address2" variant="lg" value={addressLine2} onChange={(e) => setAddressLine2(e.target.value)} />
            </FieldShell>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="pe-postcode" className="text-sm font-medium text-[#4a5565]">
                Postcode
              </Label>
              <FieldShell>
                <Input id="pe-postcode" variant="lg" value={postcode} onChange={(e) => setPostcode(e.target.value)} />
              </FieldShell>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pe-city" className="text-sm font-medium text-[#4a5565]">
                City
              </Label>
              <FieldShell>
                <Input id="pe-city" variant="lg" value={city} onChange={(e) => setCity(e.target.value)} />
              </FieldShell>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="pe-state" className="text-sm font-medium text-[#4a5565]">
                State
              </Label>
              <FieldShell>
                <Input id="pe-state" variant="lg" value={state} onChange={(e) => setState(e.target.value)} />
              </FieldShell>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pe-country" className="text-sm font-medium text-[#4a5565]">
                Country
              </Label>
              <FieldShell>
                <Input id="pe-country" variant="lg" value={country} onChange={(e) => setCountry(e.target.value)} />
              </FieldShell>
            </div>
          </div>
          <div className="grid gap-2">
            <Label className="text-sm font-medium text-[#4a5565]">Developer</Label>
            <FieldShell missing={!developerCustomerId.trim()}>
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
            </FieldShell>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pe-notes" className="text-sm font-medium text-[#4a5565]">
              Notes
            </Label>
            <FieldShell>
              <Textarea id="pe-notes" rows={3} variant="lg" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </FieldShell>
          </div>
        </CardContent>
      </Card>

    </div>
  );
}
