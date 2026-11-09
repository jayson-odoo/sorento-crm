'use client';

import { useState } from 'react';
import { LoaderCircleIcon, Plus, Trash2 } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { PhoneInput } from '@/components/common/PhoneInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  DealerAccessGrantError,
  type DealerAccessRole,
  type DealerAccessRow,
} from '@/services/dealerAccessService';
import {
  useDealerAccessGrant,
  useDealerAccessUpdate,
} from '../hooks/useDealerAccessMutations';
import { useDealerAccessAccountsQuery } from '../hooks/useDealerAccessQuery';
import { useMyDealerCompanies } from '../hooks/useMyDealerCompanies';

const MAX_PEOPLE = 20;

export const ACCESS_OPTIONS: { value: DealerAccessRole; label: string }[] = [
  { value: 'owner', label: 'Business Owner' },
  { value: 'employee', label: 'Employee' },
];

interface PersonDraft {
  key: number;
  name: string;
  phone: string;
  phoneValid: boolean;
  role: DealerAccessRole;
}

let personKey = 0;
const blankPerson = (): PersonDraft => {
  personKey += 1;
  return { key: personKey, name: '', phone: '', phoneValid: false, role: 'employee' };
};

/**
 * Add people (no `person`) or edit one (`person`), the portal form look of
 * `SalesOpportunityPortalForm`: Cards, Label + field, a People card with "+ Add person" and a
 * trash per row. A refused grant row shows its reason under its own row and the form stays.
 */
export default function DealerAccessFormDialog({
  open,
  onOpenChange,
  person,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  person?: DealerAccessRow | null;
}) {
  const editing = !!person;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{person ? person.name : 'Add people'}</DialogTitle>
        </DialogHeader>
        {open ? (
          <FormBody
            key={person?.contact_id ?? 'new'}
            person={person ?? null}
            editing={editing}
            onClose={() => onOpenChange(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function FormBody({
  person,
  editing,
  onClose,
}: {
  person: DealerAccessRow | null;
  editing: boolean;
  onClose: () => void;
}) {
  const { options: companyOptions, isLoading: companiesLoading } = useMyDealerCompanies();
  const single = !editing && companyOptions.length === 1 ? companyOptions[0].value : '';
  const [pickedCompany, setCompany] = useState(person?.company ?? '');
  const company = pickedCompany || single;
  const [accountIds, setAccountIds] = useState<string[]>(person?.accounts.map((a) => a.id) ?? []);
  const [people, setPeople] = useState<PersonDraft[]>([blankPerson()]);
  const [role, setRole] = useState<DealerAccessRole>(person?.access ?? 'employee');
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [formError, setFormError] = useState('');

  const grant = useDealerAccessGrant();
  const update = useDealerAccessUpdate();
  const saving = grant.isPending || update.isPending;

  const { data: accounts = [] } = useDealerAccessAccountsQuery(company);
  const accountOptions = [
    ...accounts,
    // The person's linked accounts show by name before (or without) the list arriving.
    ...(person?.accounts ?? []).filter((a) => !accounts.some((x) => x.id === a.id)),
  ].map((a) => ({ value: a.id, label: `${a.code} ${a.name}` }));

  const updatePerson = (key: number, patch: Partial<PersonDraft>) => {
    setPeople((prev) => prev.map((p) => (p.key === key ? { ...p, ...patch } : p)));
    setRowErrors({});
  };

  const canSave =
    !!company &&
    accountIds.length > 0 &&
    (editing || people.every((p) => p.name.trim() && p.phoneValid)) &&
    !saving;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    setFormError('');
    setRowErrors({});
    try {
      if (person) {
        await update.mutateAsync({
          contactId: person.contact_id,
          company,
          role,
          account_ids: accountIds,
        });
      } else {
        await grant.mutateAsync({
          company,
          account_ids: accountIds,
          people: people.map((p) => ({ name: p.name.trim(), phone: p.phone, role: p.role })),
        });
      }
      onClose();
    } catch (error) {
      if (error instanceof DealerAccessGrantError) setRowErrors(error.rowErrors);
      else if (editing) setFormError(error instanceof Error ? error.message : 'Failed to update access');
    }
  };

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <DialogBody className="flex flex-col gap-4 overflow-y-auto">
        <Card>
          <CardContent className="flex flex-col gap-4 pt-5">
            {editing ? (
              <>
                <ReadOnlyField label="Company" value={person?.company_name ?? ''} />
                <ReadOnlyField label="Phone" value={person?.phone ?? ''} />
              </>
            ) : companyOptions.length > 1 || (companiesLoading && !company) ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dealer-access-company">Company</Label>
                <SearchableSelect
                  id="dealer-access-company"
                  aria-label="Company"
                  value={company}
                  onChange={(v) => {
                    setCompany(v);
                    setAccountIds([]);
                  }}
                  options={companyOptions}
                  placeholder="Select a company"
                  clearable
                />
              </div>
            ) : null}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="dealer-access-accounts">My accounts</Label>
              <SearchableMultiSelect
                id="dealer-access-accounts"
                aria-label="My accounts"
                value={accountIds}
                onChange={setAccountIds}
                options={accountOptions}
                placeholder={company ? 'Select accounts' : 'Select a company first'}
                clearable
              />
            </div>
            {editing ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dealer-access-role">Access</Label>
                <SearchableSelect
                  id="dealer-access-role"
                  aria-label="Access"
                  value={role}
                  onChange={(v) => setRole((v || 'employee') as DealerAccessRole)}
                  options={ACCESS_OPTIONS}
                />
              </div>
            ) : null}
          </CardContent>
        </Card>

        {!editing ? (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>People</CardTitle>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={people.length >= MAX_PEOPLE}
                onClick={() => setPeople((prev) => [...prev, blankPerson()])}
              >
                <Plus className="size-4" />
                Add person
              </Button>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {people.map((p, index) => (
                <div key={p.key} data-testid={`person-row-${index}`} className="flex flex-col gap-2">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`person-name-${p.key}`}>Name</Label>
                    <Input
                      id={`person-name-${p.key}`}
                      value={p.name}
                      maxLength={200}
                      onChange={(e) => updatePerson(p.key, { name: e.target.value })}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`person-phone-${p.key}`}>Phone</Label>
                    <PhoneInput
                      id={`person-phone-${p.key}`}
                      aria-label={`Phone ${index + 1}`}
                      value={p.phone}
                      defaultCountry="MY"
                      onChange={(e164, meta) => updatePerson(p.key, { phone: e164, phoneValid: meta.valid })}
                    />
                  </div>
                  <div className="flex items-end gap-2">
                    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <Label htmlFor={`person-role-${p.key}`}>Access</Label>
                      <SearchableSelect
                        id={`person-role-${p.key}`}
                        aria-label={`Access ${index + 1}`}
                        value={p.role}
                        onChange={(v) => updatePerson(p.key, { role: (v || 'employee') as DealerAccessRole })}
                        options={ACCESS_OPTIONS}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove person ${index + 1}`}
                      title="Remove person"
                      disabled={people.length === 1}
                      onClick={() => {
                        setPeople((prev) => prev.filter((x) => x.key !== p.key));
                        setRowErrors({});
                      }}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                  {rowErrors[index] ? (
                    <Alert variant="destructive" appearance="light" size="sm">
                      <AlertDescription>{rowErrors[index]}</AlertDescription>
                    </Alert>
                  ) : null}
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}

        {formError ? (
          <Alert variant="destructive" appearance="light" size="sm">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={!canSave}>
          {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}
