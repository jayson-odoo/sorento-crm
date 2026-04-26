'use client';

import { useEffect, useState } from 'react';
import { Loader2, MapPin, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { createCustomer } from '@/app/(protected)/order-management/customers/services/customerService';
import type { Customer } from '@/app/(protected)/order-management/customers/types/customer.types';
import { toast } from 'sonner';
import {
  AGE_GROUPS,
  CONTACT_METHODS,
  MY_STATES,
  RACE_OPTIONS,
} from '@/app/(protected)/order-management/customers/forms/client-form-constants';

const input42 = 'h-[42px] rounded-[4px] border border-[#d1d5dc] bg-background px-3 shadow-none focus-visible:ring-1';
const input42Muted = 'h-[42px] rounded-[4px] border border-[#d1d5dc] bg-[#f3f4f6] px-3 shadow-none focus-visible:ring-1';
const select38 = 'h-[38px] w-full rounded-[4px] border border-[#d1d5dc] bg-background shadow-none focus:ring-1';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (customer: Customer) => void;
  /** Prefill “Full name” when opening from a failed client search. */
  initialFullName?: string;
};

function SectionCard({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border border-[#e5e7eb] bg-[#f9fafb] px-[25px] pb-[25px] pt-[25px]">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h3 className="text-lg font-semibold leading-7 text-[#0a0a0a]">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

export function CreateClientModal({ open, onOpenChange, onCreated, initialFullName = '' }: Props) {
  const [fullName, setFullName] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [ageGroup, setAgeGroup] = useState('');
  const [race, setRace] = useState('');
  const [referredBy, setReferredBy] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [preferContact, setPreferContact] = useState('');
  const [billAddr1, setBillAddr1] = useState('');
  const [billAddr2, setBillAddr2] = useState('');
  const [billPostcode, setBillPostcode] = useState('');
  const [billCity, setBillCity] = useState('');
  const [billState, setBillState] = useState('');
  const [billCountry, setBillCountry] = useState('Malaysia');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFullName(initialFullName || '');
    setFirstName('');
    setLastName('');
    setAgeGroup('');
    setRace('');
    setReferredBy('');
    setEmail('');
    setPhone('');
    setPreferContact('');
    setBillAddr1('');
    setBillAddr2('');
    setBillPostcode('');
    setBillCity('');
    setBillState('');
    setBillCountry('Malaysia');
  }, [open, initialFullName]);

  const openBillingMaps = () => {
    const q = [billAddr1, billCity, billState, billCountry].filter(Boolean).join(', ');
    window.open(
      q ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}` : 'https://www.google.com/maps',
      '_blank',
      'noopener,noreferrer',
    );
  };

  const handleSubmit = async () => {
    const name =
      fullName.trim() ||
      [firstName.trim(), lastName.trim()].filter(Boolean).join(' ').trim();
    if (!name) return;
    const rawCode = name.toUpperCase().replace(/[^A-Z0-9]+/g, '_').slice(0, 32) || `C${Date.now()}`;
    const noteParts = [
      referredBy.trim() && `Referred by: ${referredBy.trim()}`,
      ageGroup && `Age group: ${ageGroup}`,
      race && `Race: ${race}`,
      preferContact && `Preferred contact: ${preferContact}`,
    ].filter(Boolean);

    setPending(true);
    try {
      const row = await createCustomer({
        customer_code: rawCode,
        customer_name: name,
        email: email.trim() || undefined,
        phone_number: phone.trim() || undefined,
        is_active: true,
        country: billCountry.trim() || undefined,
        billing_address:
          billAddr1.trim() || billAddr2.trim() || billPostcode.trim() || billCity.trim() || billState.trim()
            ? {
                line_1: billAddr1.trim() || undefined,
                line_2: billAddr2.trim() || undefined,
                postcode: billPostcode.trim() || undefined,
                city: billCity.trim() || undefined,
                state: billState.trim() || undefined,
                country: billCountry.trim() || undefined,
              }
            : undefined,
        notes: noteParts.length ? noteParts.join('\n') : undefined,
      });
      onCreated(row);
      onOpenChange(false);
      setFullName('');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to create client');
    } finally {
      setPending(false);
    }
  };

  const canSubmit = !!(fullName.trim() || firstName.trim() || lastName.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="flex max-h-[90vh] max-w-[896px] w-[calc(100vw-2rem)] flex-col gap-0 overflow-hidden rounded-[10px] border-[#e5e7eb] p-0 sm:max-w-[896px]"
      >
        <div className="flex shrink-0 items-start justify-between border-b border-[#e5e7eb] px-6 pb-[25px] pt-6">
          <div className="space-y-1 pe-8">
            <DialogTitle className="text-2xl font-semibold leading-8 tracking-tight text-[#0a0a0a]">
              Create New Client
            </DialogTitle>
            <p className="text-sm leading-5 text-[#6a7282]">Add a new client to your organization</p>
          </div>
          <DialogClose asChild>
            <button
              type="button"
              className="rounded-sm text-[#0a0a0a] opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2"
              aria-label="Close"
            >
              <X className="size-6" />
            </button>
          </DialogClose>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="flex flex-col gap-8">
            <SectionCard title="Personal Information">
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label className="text-[#364153] text-sm font-medium">
                    Full Name <span className="text-[#fb2c36]">*</span>
                  </Label>
                  <Input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className={input42Muted}
                    placeholder=""
                  />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">First Name</Label>
                    <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} className={input42} />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Last Name</Label>
                    <Input value={lastName} onChange={(e) => setLastName(e.target.value)} className={input42} />
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Age Group</Label>
                    <Select value={ageGroup || '__none__'} onValueChange={(v) => setAgeGroup(v === '__none__' ? '' : v)}>
                      <SelectTrigger className={select38}>
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select</SelectItem>
                        {AGE_GROUPS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Race</Label>
                    <Select value={race || '__none__'} onValueChange={(v) => setRace(v === '__none__' ? '' : v)}>
                      <SelectTrigger className={select38}>
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select</SelectItem>
                        {RACE_OPTIONS.map((r) => (
                          <SelectItem key={r} value={r}>
                            {r}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <Label className="text-[#364153] text-sm font-medium">Referred By</Label>
                  <Input value={referredBy} onChange={(e) => setReferredBy(e.target.value)} className={input42} />
                </div>
              </div>
            </SectionCard>

            <SectionCard title="Contact Information">
              <div className="flex flex-col gap-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Email</Label>
                    <Input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className={input42}
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Phone</Label>
                    <Input value={phone} onChange={(e) => setPhone(e.target.value)} className={input42} />
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <Label className="text-[#364153] text-sm font-medium">Prefer Contact Method</Label>
                  <Select
                    value={preferContact || '__none__'}
                    onValueChange={(v) => setPreferContact(v === '__none__' ? '' : v)}
                  >
                    <SelectTrigger className={select38}>
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">Select</SelectItem>
                      {CONTACT_METHODS.map((c) => (
                        <SelectItem key={c} value={c}>
                          {c}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </SectionCard>

            <SectionCard
              title="Billing Address"
              action={
                <button
                  type="button"
                  className="flex items-center gap-1 text-sm font-medium text-[#e7000b] hover:underline"
                  onClick={openBillingMaps}
                >
                  <MapPin className="size-4 shrink-0" aria-hidden />
                  Open Maps
                </button>
              }
            >
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label className="text-[#364153] text-sm font-medium">Address Line 1</Label>
                  <Input value={billAddr1} onChange={(e) => setBillAddr1(e.target.value)} className={input42} />
                </div>
                <div className="flex flex-col gap-2">
                  <Label className="text-[#364153] text-sm font-medium">Address Line 2</Label>
                  <Input value={billAddr2} onChange={(e) => setBillAddr2(e.target.value)} className={input42} />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Postcode</Label>
                    <Input value={billPostcode} onChange={(e) => setBillPostcode(e.target.value)} className={input42} />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Area/City</Label>
                    <Input value={billCity} onChange={(e) => setBillCity(e.target.value)} className={input42} />
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">State</Label>
                    <Select value={billState || '__none__'} onValueChange={(v) => setBillState(v === '__none__' ? '' : v)}>
                      <SelectTrigger className={select38}>
                        <SelectValue placeholder="Select state" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select state</SelectItem>
                        {MY_STATES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {s}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-[#364153] text-sm font-medium">Country</Label>
                    <Select
                      value={billCountry || '__none__'}
                      onValueChange={(v) => setBillCountry(v === '__none__' ? '' : v)}
                    >
                      <SelectTrigger className={select38}>
                        <SelectValue placeholder="Select country" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select country</SelectItem>
                        <SelectItem value="Malaysia">Malaysia</SelectItem>
                        <SelectItem value="Singapore">Singapore</SelectItem>
                        <SelectItem value="Other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            </SectionCard>
          </div>
        </div>

        <div className="flex shrink-0 justify-end gap-3 border-t border-[#e5e7eb] px-6 pb-6 pt-[25px]">
          <Button
            type="button"
            variant="outline"
            className="h-[42px] min-w-[101px] rounded-md border-[#d1d5dc] px-5 text-base font-medium text-[#0a0a0a] shadow-none"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!canSubmit || pending}
            className="h-[42px] min-w-[145px] rounded-md bg-[#e7000b] px-6 text-base font-medium text-white hover:bg-[#e7000b]/90 disabled:opacity-60"
            onClick={() => void handleSubmit()}
          >
            {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : 'Create Client'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
