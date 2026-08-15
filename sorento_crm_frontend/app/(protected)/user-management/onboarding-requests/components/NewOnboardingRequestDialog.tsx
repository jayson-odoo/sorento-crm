'use client';

/**
 * Create an onboarding request (UAC AC-3.1, journey "captain side" step 0).
 *
 * A modal rather than a page: five fields, no nested entities, so it follows the
 * repo's create-is-a-modal default. It exists because the batch has to start
 * somewhere - without it the queue can only ever show requests somebody made
 * through the API, and the link the requester is waiting for is unreachable.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Loader2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { getCompaniesSelect } from '@/app/(protected)/system-management/companies/services/companyService';
import { useCreateOnboardingRequest } from '../hooks/useOnboardingRequests';

const EMPTY = {
  company_id: '',
  title: '',
  requester_name: '',
  requester_email: '',
  requester_phone: '',
};

export function NewOnboardingRequestDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(EMPTY);

  // The company decides what the approved people are granted, so it is the
  // first question and it has no default worth guessing.
  const { data: companies } = useQuery({
    queryKey: ['companies-select'],
    queryFn: getCompaniesSelect,
    enabled: open,
    staleTime: 1000 * 60 * 5,
  });

  const companyOptions = (companies ?? []).map((company) => ({
    value: company.id,
    label: company.name,
    description: company.code,
  }));

  const canSubmit =
    values.company_id.length > 0 &&
    values.title.trim().length > 0 &&
    values.requester_name.trim().length > 0 &&
    values.requester_email.trim().length > 0;

  const createMutation = useCreateOnboardingRequest();

  const submit = () => {
    createMutation.mutate(
      {
        company_id: values.company_id,
        title: values.title.trim(),
        requester_name: values.requester_name.trim(),
        requester_email: values.requester_email.trim(),
        requester_phone: values.requester_phone.trim() || null,
      },
      {
        onSuccess: (request) => {
          setOpen(false);
          setValues(EMPTY);
          // Straight to the detail page, because the next thing he needs is the
          // link, and it only exists there.
          router.push(`/user-management/onboarding-requests/${request.id}`);
        },
      },
    );
  };

  const set = (key: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setValues(EMPTY);
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus />
          New request
        </Button>
      </DialogTrigger>
      {/* Scrollable, so the Create button stays reachable at phone height. */}
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New onboarding request</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-company">Company</Label>
            <SearchableSelect
              id="onboarding-company"
              value={values.company_id}
              onChange={(value) => setValues((v) => ({ ...v, company_id: value }))}
              options={companyOptions}
              placeholder="Select a company"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-title">Title</Label>
            <Input
              id="onboarding-title"
              value={values.title}
              onChange={set('title')}
              placeholder="Staff onboarding"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-requester-name">Requester name</Label>
            <Input
              id="onboarding-requester-name"
              value={values.requester_name}
              onChange={set('requester_name')}
              placeholder="Full name"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-requester-email">Requester email</Label>
            <Input
              id="onboarding-requester-email"
              type="email"
              value={values.requester_email}
              onChange={set('requester_email')}
              placeholder="name@company.com"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-requester-phone">Requester phone</Label>
            <Input
              id="onboarding-requester-phone"
              value={values.requester_phone}
              onChange={set('requester_phone')}
              placeholder="Optional"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit || createMutation.isPending}>
            {createMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
