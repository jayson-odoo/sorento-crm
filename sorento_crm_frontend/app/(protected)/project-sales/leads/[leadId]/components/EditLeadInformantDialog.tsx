'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useFetchCustomerOptions } from '../../../_shared/hooks/useProjects';
import {
  InformantFieldset,
  informantBody,
  type InformantDraft,
} from '../../components/InformantFieldset';
import type {
  LeadInformantBody,
  LeadWithAcceptance,
} from '../../../_shared/types/leadAcceptance.types';
import type { ProjectLeadBody } from '../../../_shared/types/project.types';

/**
 * The two "who" questions on a lead, in one place and never in the same box.
 *
 * The informant told us about the job. The customer will issue the purchase order.
 *
 * There is deliberately NO owner field here. `PUT /leads/{id}` still accepts
 * `owner_user_id` (phase-1 behaviour), and editing it would move a lead to a new person
 * without a clock, a notification or an acceptance. Changing who holds a lead goes
 * through `/assign` only.
 */
export function EditLeadInformantDialog({
  lead,
  submitting,
  onDone,
  onConfirm,
}: {
  lead: LeadWithAcceptance;
  submitting?: boolean;
  onDone: () => void;
  onConfirm: (
    body: Partial<ProjectLeadBody> & LeadInformantBody,
  ) => Promise<void>;
}) {
  const fetchCustomers = useFetchCustomerOptions();
  const [informant, setInformant] = React.useState<InformantDraft>({
    informant_source: lead.informant_source ?? '',
    informant_ref: lead.informant_ref ?? '',
    informant_contact_name: lead.informant_contact_name ?? '',
  });
  const [customerId, setCustomerId] = React.useState(lead.customer_id ?? '');
  const [busy, setBusy] = React.useState(false);
  const pending = busy || Boolean(submitting);

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Who told us, and the customer</DialogTitle>
          <DialogDescription>{lead.title}</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            try {
              await onConfirm({
                ...informantBody(informant),
                customer_id: customerId || null,
              });
              onDone();
            } finally {
              setBusy(false);
            }
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            <InformantFieldset
              value={informant}
              onChange={setInformant}
              idPrefix="edit-informant"
            />

            <div className="space-y-1.5">
              <Label htmlFor="edit-lead-customer">Customer</Label>
              <SearchableSelect
                id="edit-lead-customer"
                value={customerId}
                onChange={setCustomerId}
                clearable={!lead.customer_id}
                fetchOptions={fetchCustomers}
                selectedOption={
                  lead.customer_id && lead.customer_name
                    ? { value: lead.customer_id, label: lead.customer_name }
                    : undefined
                }
                placeholder="Search customers"
                emptyMessage="No customers found"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              Save informant
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
