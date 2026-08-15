'use client';

/**
 * Create an onboarding request (UAC AC-3.1, journey "captain side" step 0).
 *
 * A modal rather than a page: four fields, no nested entities, so it follows the
 * repo's create-is-a-modal default. It exists because the batch has to start
 * somewhere - without it the queue can only ever show requests somebody made
 * through the API, and the link the requester is waiting for is unreachable.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';
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
import { createOnboardingRequest } from '../services/onboardingService';

const EMPTY = {
  title: '',
  requester_name: '',
  requester_email: '',
  requester_phone: '',
};

export function NewOnboardingRequestDialog() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(EMPTY);

  const canSubmit =
    values.title.trim().length > 0 &&
    values.requester_name.trim().length > 0 &&
    values.requester_email.trim().length > 0;

  const createMutation = useMutation({
    mutationFn: () =>
      createOnboardingRequest({
        title: values.title.trim(),
        requester_name: values.requester_name.trim(),
        requester_email: values.requester_email.trim(),
        requester_phone: values.requester_phone.trim() || null,
      }),
    onSuccess: (request) => {
      queryClient.invalidateQueries({ queryKey: ['onboarding-requests'] });
      setOpen(false);
      setValues(EMPTY);
      toast.success('Request created. Send the link from here.');
      // Straight to the detail page, because the next thing he needs is the
      // link, and it only exists there.
      router.push(`/user-management/onboarding-requests/${request.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

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
          <Plus className="size-4 mr-2" />
          New request
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New onboarding request</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-title">What is this batch</Label>
            <Input
              id="onboarding-title"
              value={values.title}
              onChange={set('title')}
              placeholder="MOCHA staff onboarding"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-requester-name">Who are you asking</Label>
            <Input
              id="onboarding-requester-name"
              value={values.requester_name}
              onChange={set('requester_name')}
              placeholder="Esther Lim"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-requester-email">Their email</Label>
            <Input
              id="onboarding-requester-email"
              type="email"
              value={values.requester_email}
              onChange={set('requester_email')}
              placeholder="esther@mocha.com.my"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="onboarding-requester-phone">Their phone (optional)</Label>
            <Input
              id="onboarding-requester-phone"
              value={values.requester_phone}
              onChange={set('requester_phone')}
              placeholder="012-3456789"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={!canSubmit || createMutation.isPending}
          >
            {createMutation.isPending ? <Loader2 className="size-4 mr-2 animate-spin" /> : null}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
