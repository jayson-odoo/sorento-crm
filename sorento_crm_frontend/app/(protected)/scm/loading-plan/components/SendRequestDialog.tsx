'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircle, Mail, MessageCircle, Send, X } from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { fmtInt } from '../../lib/format';
import { useSupplierChatContacts } from '../../hooks/useFulfilment';
import type { CodedError } from '../../services/fulfilmentService';

/**
 * "Send this request" (R9, AC-C1 to AC-C5).
 *
 * Replaces the bare confirm dialog, because a send now has two decisions in it that the
 * confirm could not carry: WHICH channel it goes on, and WHO on that channel it is addressed
 * to. Both were fixed before: email, to `suppliers.email` and nobody else.
 *
 * The two channels are exclusive by design (R9): one send writes ONE notice, so the panel
 * under the radio is the one being sent on. Until S3 a chat row was written on every send and
 * always read `skipped`, which is a record that always says "not done".
 *
 * The refusal is shown HERE, in the dialog, not as a toast: every one of the eight refusals
 * names something on this form that can be changed (an address, a contact, a channel), and a
 * toast says it where it cannot be acted on and then takes it away again.
 */

/** RFC-shaped enough to catch the mistakes people actually make (no @, trailing comma, a
 *  space in the middle). Deliberately not a full grammar: the server validates with
 *  `EmailStr`, and a browser-side rule stricter than the server's would refuse addresses that
 *  work. */
const EMAIL_RE = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]{2,}$/;

/** The backend's `code` turned into the sentence that says what to do about it (AC-C5). The
 *  server's own message is used for anything not listed - a code this map has not heard of is
 *  still a real refusal and must not be swallowed. */
const REFUSAL_TEXT: Record<string, string> = {
  no_recipients: 'Add at least one address before sending.',
  invalid_recipient: 'One of these addresses is not a valid email address.',
  unknown_channel: 'That channel does not exist. Choose Email or Chat.',
  wechat_channel_missing:
    'No WeChat channel is connected in the Respond.io workspace, so a chat send cannot go out. Send by email, or ask an admin to connect the channel.',
  chat_contact_required: 'Choose the WeChat contact this should go to.',
  chat_contact_not_found: 'That WeChat contact no longer exists. Pick another one.',
  chat_contact_unreachable:
    'That contact cannot be reached on WeChat right now. Send by email instead.',
  template_missing:
    'This contact is outside the 24-hour window and no approved template is mapped to supplier requests, so nothing can be delivered. Send by email instead.',
};

export interface SendRequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  supplierId: string;
  supplierName: string;
  /** The address the To field opens with. Null when the supplier has none on file - the
   *  dialog then opens with no chips and Send disabled, which is the honest state. */
  supplierEmail: string | null;
  /** What is being sent, for the header line: how many products and how many units. */
  lineCount: number;
  totalQty: number;
  /** Typed quantities not yet written. Named in the header, because Send saves first (AC-A15). */
  unsavedCount: number;
  isBusy: boolean;
  /** The last refusal from the server, or null. Held by the caller because the mutation is. */
  error: CodedError | Error | null;
  onSend: (payload: {
    channel: 'email' | 'chat';
    recipients: string[];
    chatContactId: string | null;
    note: string;
  }) => void;
}

export function SendRequestDialog({
  open,
  onOpenChange,
  supplierId,
  supplierName,
  supplierEmail,
  lineCount,
  totalQty,
  unsavedCount,
  isBusy,
  error,
  onSend,
}: SendRequestDialogProps) {
  const [channel, setChannel] = useState<'email' | 'chat'>('email');
  const [recipients, setRecipients] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [draftError, setDraftError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [chatContactId, setChatContactId] = useState('');
  const [chatQuery, setChatQuery] = useState('');

  // Reopened, not remounted: the dialog lives beside the toolbar button, so a stale set of
  // chips from the last send would otherwise be what the next one goes out to.
  useEffect(() => {
    if (!open) return;
    setChannel('email');
    setRecipients(supplierEmail ? [supplierEmail] : []);
    setDraft('');
    setDraftError(null);
    setNote('');
    setChatContactId('');
    setChatQuery('');
  }, [open, supplierEmail]);

  const contacts = useSupplierChatContacts(supplierId, chatQuery, open && channel === 'chat');
  const chatConnected = contacts.data?.wechat_connected ?? true;
  const chatUnavailable = contacts.data?.unavailable_reason ?? null;

  const chatOptions = useMemo(
    () =>
      (contacts.data?.data ?? []).map((c) => ({
        value: c.id,
        label: c.name || c.phone || 'Unnamed contact',
        description: c.suggested
          ? `${c.phone ?? ''} · this supplier's own number`.trim()
          : (c.phone ?? undefined),
        searchText: [c.name, c.phone].filter(Boolean).join(' '),
      })),
    [contacts.data],
  );

  // The supplier's own number, preselected (AC-C3). Only while nothing has been chosen, so
  // typing a search never yanks the selection back to the suggestion.
  useEffect(() => {
    if (channel !== 'chat' || chatContactId) return;
    const suggested = (contacts.data?.data ?? []).find((c) => c.suggested);
    if (suggested) setChatContactId(suggested.id);
  }, [channel, chatContactId, contacts.data]);

  const addRecipient = () => {
    const value = draft.trim();
    if (!value) return;
    if (!EMAIL_RE.test(value)) {
      setDraftError(`${value} is not an email address.`);
      return;
    }
    if (recipients.some((r) => r.toLowerCase() === value.toLowerCase())) {
      setDraftError('That address is already on the list.');
      return;
    }
    setRecipients((prev) => [...prev, value]);
    setDraft('');
    setDraftError(null);
  };

  const canSend =
    !isBusy &&
    (channel === 'email' ? recipients.length > 0 : chatConnected && !!chatContactId);

  const refusal = (() => {
    if (!error) return null;
    const code = (error as CodedError).code;
    return (code && REFUSAL_TEXT[code]) || error.message;
  })();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Send this request</DialogTitle>
          <DialogDescription>
            {fmtInt(lineCount)} product{lineCount === 1 ? '' : 's'}, {fmtInt(totalQty)} units to{' '}
            {supplierName}.
            {unsavedCount > 0 ? ' Your typed quantities are saved first.' : ''}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          <RadioGroup
            value={channel}
            onValueChange={(next) => {
              setChannel(next as 'email' | 'chat');
              setDraftError(null);
            }}
            className="grid-cols-1 sm:grid-cols-2"
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem value="email" id="send-channel-email" disabled={isBusy} />
              <Label htmlFor="send-channel-email" className="text-sm font-normal">
                Email
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="chat" id="send-channel-chat" disabled={isBusy} />
              <Label htmlFor="send-channel-chat" className="text-sm font-normal">
                Chat (WeChat)
              </Label>
            </div>
          </RadioGroup>

          {channel === 'email' ? (
            <div data-testid="send-email-panel">
              <Label htmlFor="send-add-address" className="mb-1 block text-xs">
                To
              </Label>
              {recipients.length === 0 ? (
                <p className="mb-2 text-2xs text-muted-foreground">
                  No address on file for {supplierName}. Add one to send.
                </p>
              ) : (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {recipients.map((address) => (
                    <span
                      key={address}
                      className="inline-flex max-w-full items-center gap-1 rounded-md border bg-muted/40 px-2 py-1 text-2xs"
                    >
                      <span className="truncate" title={address}>
                        {address}
                      </span>
                      <button
                        type="button"
                        aria-label={`Remove ${address}`}
                        className="text-muted-foreground hover:text-foreground"
                        disabled={isBusy}
                        onClick={() =>
                          setRecipients((prev) => prev.filter((r) => r !== address))
                        }
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  id="send-add-address"
                  type="email"
                  className="w-full sm:w-72"
                  placeholder="Add an address"
                  value={draft}
                  disabled={isBusy}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    setDraftError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key !== 'Enter') return;
                    // Enter adds the address; it must not submit the dialog with an address
                    // still sitting unadded in the box.
                    e.preventDefault();
                    addRecipient();
                  }}
                />
                <Button variant="outline" size="sm" disabled={isBusy} onClick={addRecipient}>
                  Add
                </Button>
              </div>
              {draftError ? (
                <p className="mt-1 text-2xs text-destructive" role="alert">
                  {draftError}
                </p>
              ) : null}
            </div>
          ) : (
            <div data-testid="send-chat-panel">
              <Label htmlFor="send-chat-contact" className="mb-1 block text-xs">
                WeChat contact
              </Label>
              <SearchableSelect
                id="send-chat-contact"
                value={chatContactId}
                onChange={setChatContactId}
                options={chatOptions}
                onSearchChange={setChatQuery}
                placeholder="Choose a contact"
                emptyMessage={`No WeChat contact for ${supplierName} yet`}
                className="w-full"
                clearable
                disabled={isBusy || !chatConnected}
              />
              {!chatConnected ? (
                <p className="mt-1 text-2xs text-destructive" role="alert">
                  {chatUnavailable ??
                    'No WeChat channel is connected in the Respond.io workspace.'}
                </p>
              ) : null}
            </div>
          )}

          <div>
            <Label htmlFor="send-note" className="mb-1 block text-xs">
              Note (optional)
            </Label>
            <Textarea
              id="send-note"
              rows={2}
              maxLength={2000}
              placeholder="Please confirm by Friday"
              value={note}
              disabled={isBusy}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>

          {/* What actually leaves the building, stated before it does. The retired link is the
              part that surprises people: a second send makes the first link stop answering. */}
          <p className="text-2xs text-muted-foreground">
            {channel === 'email' ? (
              <Mail className="mr-1 inline size-3" />
            ) : (
              <MessageCircle className="mr-1 inline size-3" />
            )}
            PDF + XLSX attached · link included · the previous link is retired
          </p>

          {refusal ? (
            <p
              className={cn('rounded-md border border-destructive/40 p-2 text-xs text-destructive')}
              role="alert"
              data-testid="send-refusal"
            >
              {refusal}
            </p>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" disabled={isBusy} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!canSend}
            data-testid="send-confirm"
            onClick={() =>
              onSend({
                channel,
                recipients,
                chatContactId: channel === 'chat' ? chatContactId || null : null,
                note,
              })
            }
          >
            {isBusy ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
            Send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SendRequestDialog;
