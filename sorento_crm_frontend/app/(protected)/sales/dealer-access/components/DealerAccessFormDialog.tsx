'use client';

import { useState } from 'react';
import { LoaderCircleIcon, Plus, RefreshCw, Trash2 } from 'lucide-react';
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
  type DealerAccessRefusedContact,
  type DealerAccessRole,
  type DealerAccessRow,
} from '@/services/dealerAccessService';
import {
  useDealerAccessGrant,
  useDealerAccessRespondRetry,
  useDealerAccessUpdate,
} from '../hooks/useDealerAccessMutations';
import {
  useDealerAccessAccountsForCompanies,
  useFindDealerAccessPerson,
} from '../hooks/useDealerAccessQuery';
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

/** "Not yet in Respond.io: <reason>." (N5.3), whatever punctuation the reason came with. */
export function notInRespondText(reason: string | null | undefined): string {
  const why = (reason || 'Respond.io gave no answer').trim().replace(/\.+$/, '');
  return `Not yet in Respond.io: ${why}.`;
}

const accessLabel = (row: DealerAccessRow) =>
  row.access === 'owner' ? (row.owner_tag ?? 'Business Owner') : 'Employee';

let personKey = 0;
const blankPerson = (): PersonDraft => {
  personKey += 1;
  return { key: personKey, name: '', phone: '', phoneValid: false, role: 'employee' };
};

/**
 * Add people (no `person`), edit one (`person`), or show one read-only (`person.editable` false:
 * the same fields as values, no Save, N2.5). The portal form look of `SalesOpportunityPortalForm`:
 * Cards, Label + field, a People card with "+ Add person" and a trash per row. A refused grant
 * row shows its reason under its own row and the form stays; an "already has access" refusal
 * offers "Edit / Show <Name>", which opens that person here (N4.3).
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
  // A person opened from a refused row replaces the form until the dialog closes.
  const [opened, setOpened] = useState<DealerAccessRow | null>(null);
  if (!open && opened) setOpened(null);
  const current = opened ?? person ?? null;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setOpened(null);
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{current ? current.name : 'Add people'}</DialogTitle>
        </DialogHeader>
        {open ? (
          <FormBody
            key={current ? `${current.contact_id}:${current.company}` : 'new'}
            person={current}
            onOpenPerson={setOpened}
            onClose={() => {
              setOpened(null);
              onOpenChange(false);
            }}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function FormBody({
  person,
  onOpenPerson,
  onClose,
}: {
  person: DealerAccessRow | null;
  onOpenPerson: (row: DealerAccessRow) => void;
  onClose: () => void;
}) {
  const editing = !!person;
  const readOnly = !!person && !person.editable;
  const { options: companyOptions, isLoading: companiesLoading } = useMyDealerCompanies();
  const companyName = (code: string) => companyOptions.find((o) => o.value === code)?.label ?? code;
  const single = !editing && companyOptions.length === 1 ? companyOptions[0].value : '';
  const [pickedCompanies, setPickedCompanies] = useState<string[]>([]);
  const companies = editing
    ? [person.company]
    : pickedCompanies.length
      ? pickedCompanies
      : single
        ? [single]
        : [];
  const [accountIds, setAccountIds] = useState<string[]>(
    person?.accounts.filter((a) => a.mine).map((a) => a.id) ?? [],
  );
  const [people, setPeople] = useState<PersonDraft[]>([blankPerson()]);
  const [role, setRole] = useState<DealerAccessRole>(person?.access ?? 'employee');
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [rowContacts, setRowContacts] = useState<Record<number, DealerAccessRefusedContact>>({});
  const [formError, setFormError] = useState('');
  // After a grant: the people Respond.io does not have yet, by row (N5.3). Access is already given.
  const [notInRespond, setNotInRespond] = useState<
    Record<number, { contactId: string; error: string | null }> | null
  >(null);

  const grant = useDealerAccessGrant();
  const update = useDealerAccessUpdate();
  const retry = useDealerAccessRespondRetry();
  const findPerson = useFindDealerAccessPerson();
  const saving = grant.isPending || update.isPending;

  const accountsByCompany = useDealerAccessAccountsForCompanies(readOnly ? [] : companies);
  const listed = companies.flatMap((code) =>
    (accountsByCompany[code] ?? []).map((a) => ({ ...a, company: code })),
  );
  const accountOptions = [
    ...listed,
    // The person's own linked accounts show by name before (or without) the list arriving.
    ...(person?.accounts ?? [])
      .filter((a) => a.mine && !listed.some((x) => x.id === a.id))
      .map((a) => ({ ...a, company: person?.company ?? '' })),
  ].map((a) => ({
    value: a.id,
    label: `${a.name} (${a.code})`,
    group: companies.length > 1 ? companyName(a.company) : undefined,
  }));
  const theirs = person?.accounts.filter((a) => !a.mine) ?? [];

  const pickCompanies = (next: string[]) => {
    setPickedCompanies(next);
    setAccountIds((prev) =>
      prev.filter((id) => next.some((code) => (accountsByCompany[code] ?? []).some((a) => a.id === id))),
    );
  };

  const updatePerson = (key: number, patch: Partial<PersonDraft>) => {
    setPeople((prev) => prev.map((p) => (p.key === key ? { ...p, ...patch } : p)));
    setRowErrors({});
    setRowContacts({});
  };

  // Every picked company needs one of my accounts (N4.1).
  const covered =
    companies.length > 0 &&
    (editing
      ? accountIds.length > 0
      : companies.every((code) => (accountsByCompany[code] ?? []).some((a) => accountIds.includes(a.id))));
  const canSave =
    !readOnly &&
    !notInRespond &&
    covered &&
    (editing || people.every((p) => p.name.trim() && p.phoneValid)) &&
    !saving;

  const openRefused = async (contact: DealerAccessRefusedContact, phone: string) => {
    const found = await findPerson(contact.id, contact.company, phone).catch(() => null);
    onOpenPerson(
      found ?? {
        // Not on the list as it stands: shown read-only with what is known.
        contact_id: contact.id,
        name: contact.name,
        phone,
        company: contact.company,
        company_name: companyName(contact.company),
        accounts: [],
        access: 'employee',
        owner_tag: null,
        editable: false,
        in_respond: true,
      },
    );
  };

  const tryRespondAgain = (index: number, contactId: string) =>
    retry.mutate(contactId, {
      onSuccess: (result) =>
        setNotInRespond((prev) => {
          const next = { ...(prev ?? {}) };
          if (result.respond === 'ok') delete next[index];
          else next[index] = { contactId, error: result.respond_error };
          return next;
        }),
    });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave || !person && companies.length === 0) return;
    setFormError('');
    setRowErrors({});
    setRowContacts({});
    try {
      if (person) {
        await update.mutateAsync({
          contactId: person.contact_id,
          company: person.company,
          role,
          account_ids: accountIds,
        });
        onClose();
        return;
      }
      const result = await grant.mutateAsync({
        companies,
        account_ids: accountIds,
        people: people.map((p) => ({ name: p.name.trim(), phone: p.phone, role: p.role })),
      });
      const failed = Object.fromEntries(
        (result.rows ?? [])
          .filter((r) => r.respond === 'failed')
          .map((r) => [r.index, { contactId: r.contact_id, error: r.respond_error }]),
      );
      // Not silent (N5.3): the dialog stays to say who Respond.io does not have yet.
      if (Object.keys(failed).length) setNotInRespond(failed);
      else onClose();
    } catch (error) {
      if (error instanceof DealerAccessGrantError) {
        setRowErrors(error.rowErrors);
        setRowContacts(error.rowContacts);
      } else if (editing) setFormError(error instanceof Error ? error.message : 'Failed to update access');
    }
  };

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <DialogBody className="flex flex-col gap-4 overflow-y-auto">
        <Card>
          <CardContent className="flex flex-col gap-4 pt-5">
            {editing ? (
              <>
                <ReadOnlyField label="Company" value={person.company_name} />
                <ReadOnlyField label="Phone" value={person.phone} />
              </>
            ) : companyOptions.length > 1 || (companiesLoading && companies.length === 0) ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dealer-access-company">Company</Label>
                <SearchableMultiSelect
                  id="dealer-access-company"
                  aria-label="Company"
                  value={pickedCompanies}
                  onChange={pickCompanies}
                  options={companyOptions}
                  max={2}
                  placeholder="Select a company"
                  clearable
                />
              </div>
            ) : null}
            {readOnly ? (
              <ReadOnlyList
                label="Customers"
                values={person.accounts.map((a) => `${a.name} (${a.code})`)}
              />
            ) : (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dealer-access-accounts">My accounts</Label>
                <SearchableMultiSelect
                  id="dealer-access-accounts"
                  aria-label="My accounts"
                  value={accountIds}
                  onChange={setAccountIds}
                  options={accountOptions}
                  placeholder={companies.length ? 'Select accounts' : 'Select a company first'}
                  clearable
                />
              </div>
            )}
            {editing && !readOnly && theirs.length > 0 ? (
              <ReadOnlyList label="Other customers" values={theirs.map((a) => `${a.name} (${a.code})`)} />
            ) : null}
            {readOnly ? <ReadOnlyField label="Access" value={accessLabel(person)} /> : null}
            {editing && !readOnly ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dealer-access-role">Access</Label>
                <SearchableSelect
                  id="dealer-access-role"
                  aria-label="Access"
                  value={role}
                  onChange={(v) => setRole((v || 'employee') as DealerAccessRole)}
                  options={ACCESS_OPTIONS}
                />
                {formError ? (
                  <Alert variant="destructive" appearance="light" size="sm">
                    <AlertDescription>{formError}</AlertDescription>
                  </Alert>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {!editing && notInRespond ? (
          <Card>
            <CardContent className="flex flex-col gap-3 pt-5">
              {Object.keys(notInRespond).length === 0 ? (
                <span className="text-sm">Everyone is in Respond.io now.</span>
              ) : (
                Object.entries(notInRespond).map(([index, f]) => (
                  <div key={index} className="flex flex-col gap-1.5">
                    <span className="text-sm font-medium">{people[Number(index)]?.name.trim()}</span>
                    <Alert variant="warning" appearance="light" size="sm">
                      <AlertDescription>{`Access given. ${notInRespondText(f.error)}`}</AlertDescription>
                    </Alert>
                    <div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={retry.isPending}
                        onClick={() => tryRespondAgain(Number(index), f.contactId)}
                      >
                        <RefreshCw className="size-4" />
                        Try again
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        ) : null}

        {!editing && !notInRespond ? (
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
                        setRowContacts({});
                      }}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                  {rowErrors[index] ? (
                    <Alert variant="destructive" appearance="light" size="sm">
                      <AlertDescription className="flex flex-col items-start gap-1">
                        <span>{rowErrors[index]}</span>
                        {rowContacts[index] ? (
                          <Button
                            type="button"
                            variant="ghost"
                            mode="link"
                            underlined="dashed"
                            onClick={() => void openRefused(rowContacts[index], p.phone)}
                          >
                            {`${rowContacts[index].editable ? 'Edit' : 'Show'} ${rowContacts[index].name}`}
                          </Button>
                        ) : null}
                      </AlertDescription>
                    </Alert>
                  ) : null}
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </DialogBody>
      <DialogFooter className="gap-2">
        {readOnly || notInRespond ? (
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
        ) : (
          <>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!canSave}>
              {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
              Save
            </Button>
          </>
        )}
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

function ReadOnlyList({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {values.length ? (
        <ul className="flex flex-col gap-0.5 text-sm font-medium">
          {values.map((v) => (
            <li key={v} className="truncate" title={v}>
              {v}
            </li>
          ))}
        </ul>
      ) : (
        <span className="text-sm text-muted-foreground">None</span>
      )}
    </div>
  );
}
