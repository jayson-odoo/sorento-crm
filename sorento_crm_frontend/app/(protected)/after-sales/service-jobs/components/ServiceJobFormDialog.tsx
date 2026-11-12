'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { PhoneInput } from '@/components/common/PhoneInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useHasPermission } from '@/hooks/usePermissions';
import { searchComplaintNumbers } from '../services/serviceJobService';
import type { ServiceJob, ServiceJobFormValues } from '../types/serviceJob.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present = Edit; the same dialog and fields as Create. */
  job?: ServiceJob | null;
  onSubmit: (values: ServiceJobFormValues) => void | Promise<void>;
  isSubmitting?: boolean;
}

const text = (v: string | null | undefined) => v ?? '';
const orNull = (v: string) => v.trim() || null;

export default function ServiceJobFormDialog({ open, onOpenChange, job, onSubmit, isSubmitting }: Props) {
  const canPickComplaint = useHasPermission('complaint_management.complaints.view');
  const [f, setF] = useState({
    customer_name: '',
    contact_name: '',
    site_address_line1: '',
    site_address_line2: '',
    site_postcode: '',
    site_city: '',
    site_state: '',
    site_country: 'Malaysia',
    problem: '',
  });
  const [phone, setPhone] = useState({ e164: '', valid: true });
  const [complaint, setComplaint] = useState<{ id: string; label: string } | null>(null);
  const [tried, setTried] = useState(false);
  const [complaintQuery, setComplaintQuery] = useState('');
  // What the form was last filled for. A refetched job object is a new reference for the same job and
  // must not wipe what is being typed.
  const [filledFor, setFilledFor] = useState<string | null>(null);
  const { data: found = [] } = useQuery({
    queryKey: ['service-job-complaint-search', complaintQuery],
    queryFn: () => searchComplaintNumbers(complaintQuery),
    enabled: open && canPickComplaint,
    staleTime: 30_000,
  });
  // Static options (the pattern every other select in a dialog uses), widened by the server search.
  const complaintOptions = useMemo(() => {
    const options = found.map((c) => ({ value: c.id, label: c.complaint_number }));
    if (complaint && !options.some((o) => o.value === complaint.id)) {
      options.unshift({ value: complaint.id, label: complaint.label });
    }
    return options;
  }, [found, complaint]);

  useEffect(() => {
    const key = open ? (job?.id ?? 'new') : null;
    if (key === filledFor) return;
    setFilledFor(key);
    if (!key) return;
    setF({
      customer_name: text(job?.customer_name),
      contact_name: text(job?.contact_name),
      site_address_line1: text(job?.site_address_line1),
      site_address_line2: text(job?.site_address_line2),
      site_postcode: text(job?.site_postcode),
      site_city: text(job?.city),
      site_state: text(job?.site_state),
      site_country: job ? text(job.site_country) : 'Malaysia',
      problem: text(job?.problem),
    });
    setPhone({ e164: text(job?.contact_phone), valid: true });
    setComplaint(job?.complaint_id ? { id: job.complaint_id, label: job.complaint_number ?? '' } : null);
    setTried(false);
  }, [open, job, filledFor]);

  const set = (key: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setF((prev) => ({ ...prev, [key]: e.target.value }));

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!f.customer_name.trim() || !phone.valid) return;
    void onSubmit({
      customer_name: f.customer_name.trim(),
      contact_name: orNull(f.contact_name),
      contact_phone: phone.e164 || null,
      site_address_line1: orNull(f.site_address_line1),
      site_address_line2: orNull(f.site_address_line2),
      site_postcode: orNull(f.site_postcode),
      site_city: orNull(f.site_city),
      site_state: orNull(f.site_state),
      site_country: orNull(f.site_country),
      problem: orNull(f.problem),
      complaint_id: complaint?.id ?? null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{job ? 'Edit service job' : 'Create service job'}</DialogTitle>
          <DialogDescription className="sr-only">Service job details.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4">
          <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
          <div className="space-y-1">
            <Label htmlFor="sj-customer">Customer name *</Label>
            <Input id="sj-customer" value={f.customer_name} onChange={set('customer_name')} />
            {tried && !f.customer_name.trim() && (
              <p role="alert" className="text-sm text-destructive">
                Customer name is required.
              </p>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="sj-contact">Contact on site</Label>
              <Input id="sj-contact" value={f.contact_name} onChange={set('contact_name')} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sj-phone">Contact phone</Label>
              <PhoneInput
                id="sj-phone"
                value={phone.e164}
                showError={tried}
                errorMessage="Enter a valid phone number, e.g. 12-345 6789."
                onChange={(e164, meta) => setPhone({ e164, valid: !e164 || meta.valid })}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="sj-line1">Address line 1</Label>
            <Input id="sj-line1" value={f.site_address_line1} onChange={set('site_address_line1')} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sj-line2">Address line 2</Label>
            <Input id="sj-line2" value={f.site_address_line2} onChange={set('site_address_line2')} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="sj-postcode">Postcode</Label>
              <Input id="sj-postcode" value={f.site_postcode} onChange={set('site_postcode')} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sj-city">City</Label>
              <Input id="sj-city" value={f.site_city} onChange={set('site_city')} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sj-state">State</Label>
              <Input id="sj-state" value={f.site_state} onChange={set('site_state')} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sj-country">Country</Label>
              <Input id="sj-country" value={f.site_country} onChange={set('site_country')} />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="sj-problem">Problem</Label>
            <Textarea id="sj-problem" rows={3} value={f.problem} onChange={set('problem')} />
          </div>
          {canPickComplaint && (
            <div className="space-y-1">
              <Label>Related complaint</Label>
              <SearchableSelect
                value={complaint?.id ?? ''}
                onChange={(v) => {
                  const picked = complaintOptions.find((o) => o.value === v);
                  setComplaint(picked ? { id: picked.value, label: picked.label } : null);
                }}
                options={complaintOptions}
                onSearchChange={setComplaintQuery}
                placeholder="Search complaint number"
                aria-label="Related complaint"
                clearable
              />
            </div>
          )}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
