'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { DEMAND_CLASS_OPTIONS } from '../lib/demandClass';
import type { SalesAgent, SalesAgentAnnotationPayload } from '../types/salesAgent.types';

interface EditSalesAgentModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent: SalesAgent | null;
  isSaving?: boolean;
  onSave: (data: SalesAgentAnnotationPayload) => Promise<unknown> | unknown;
}

/**
 * The whole edit surface for an agent: the three annotation columns and nothing else.
 *
 * The code itself is not editable - it is what the documents state, and changing it
 * would strand every order that names it - so it is shown as the modal's subject rather
 * than as a field. `location_group` is free text (not a closed vocabulary like demand
 * class): a new ownership group is a warehouse suffix someone starts using, upper-cased
 * on save so it compares equal to the suffix `sales_agent_service.group_of_warehouse_code`
 * reads off a code like `BRW-BB`.
 */
export function EditSalesAgentModal({
  open,
  onOpenChange,
  agent,
  isSaving = false,
  onSave,
}: EditSalesAgentModalProps) {
  const [personLabel, setPersonLabel] = useState('');
  const [demandClass, setDemandClass] = useState('');
  const [locationGroup, setLocationGroup] = useState('');

  useEffect(() => {
    if (!open) return;
    setPersonLabel(agent?.person_label ?? '');
    setDemandClass(agent?.demand_class ?? '');
    setLocationGroup(agent?.location_group ?? '');
  }, [open, agent]);

  const submit = async () => {
    const trimmed = personLabel.trim();
    const trimmedGroup = locationGroup.trim();
    await onSave({
      person_label: trimmed ? trimmed : null,
      demand_class: demandClass ? demandClass : null,
      location_group: trimmedGroup ? trimmedGroup.toUpperCase() : null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{agent ? `Edit ${agent.sales_agent}` : 'Edit sales agent'}</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-5">
          <div>
            <Label htmlFor="sales-agent-person-label" className="mb-1 block">
              Person
            </Label>
            <Input
              id="sales-agent-person-label"
              value={personLabel}
              onChange={(e) => setPersonLabel(e.target.value)}
              // The column is varchar(100) and the backend refuses more; stop it here so
              // the limit is felt while typing rather than as a rejected save.
              maxLength={100}
              placeholder="Who this code belongs to"
            />
          </div>

          <div>
            <Label htmlFor="sales-agent-demand-class" className="mb-1 block">
              Demand class
            </Label>
            <SearchableSelect
              id="sales-agent-demand-class"
              value={demandClass}
              onChange={setDemandClass}
              options={DEMAND_CLASS_OPTIONS}
              clearable
              placeholder="Not set"
              emptyMessage="No demand classes."
            />
          </div>

          <div>
            <Label htmlFor="sales-agent-location-group" className="mb-1 block">
              Location group
            </Label>
            <Input
              id="sales-agent-location-group"
              value={locationGroup}
              onChange={(e) => setLocationGroup(e.target.value)}
              maxLength={16}
              placeholder="Not set"
            />
          </div>
        </DialogBody>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {/*
            A refused save (a class the policy cannot weigh, a label past 100 chars) rejects
            here. The mutation hook has already toasted the message, so this only swallows
            the unhandled rejection - and the modal deliberately stays open on the way out,
            so the user can correct the field they were refused on.
          */}
          <Button
            type="button"
            onClick={() => void submit().catch(() => undefined)}
            disabled={isSaving || !agent}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
