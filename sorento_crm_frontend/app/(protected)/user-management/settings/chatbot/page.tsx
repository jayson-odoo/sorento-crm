'use client';

import { useEffect, useState } from 'react';
import { RiErrorWarningFill } from '@remixicon/react';
import { LoaderCircleIcon, XIcon } from 'lucide-react';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';

import { useChatbotLanes, useChatbotSettings, useSaveChatbotSettings } from './hooks/useChatbotSettings';
import type { ChatbotSettings } from './services/chatbotSettingsService';

/**
 * Settings -> Chatbot (AC-809, AC-810).
 *
 * Which lanes the CRM finishes, the two switches that used to be environment flags,
 * and the domains the bot refuses. All four are read per turn by the engine, so a
 * change here takes effect on the next WhatsApp message with no deploy.
 */

export default function ChatbotSettingsPage() {
  const lanesQuery = useChatbotLanes();
  const settingsQuery = useChatbotSettings();
  const save = useSaveChatbotSettings();

  const [draft, setDraft] = useState<ChatbotSettings | null>(null);
  const [newDomain, setNewDomain] = useState('');
  const [orderingConfirmOpen, setOrderingConfirmOpen] = useState(false);

  useEffect(() => {
    if (settingsQuery.data && draft === null) setDraft(settingsQuery.data);
  }, [settingsQuery.data, draft]);

  // The failed load is checked FIRST. A load that fails leaves `draft` null, so a
  // loading check that also covered `!draft` would win every time and the operator
  // would wait on skeletons that never resolve.
  if ((settingsQuery.isError || lanesQuery.isError) && !draft) {
    return (
      <Alert variant="mono" icon="destructive">
        <AlertIcon>
          <RiErrorWarningFill />
        </AlertIcon>
        <AlertTitle>
          Chatbot settings could not be loaded. Reload the page to try again.
        </AlertTitle>
      </Alert>
    );
  }

  if (settingsQuery.isLoading || lanesQuery.isLoading || !draft) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const lanes = lanesQuery.data ?? [];
  const set = <K extends keyof ChatbotSettings>(key: K, value: ChatbotSettings[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  const toggleLane = (kind: string, checked: boolean) =>
    set(
      'chatbot_completed_lanes',
      checked
        ? [...draft.chatbot_completed_lanes, kind]
        : draft.chatbot_completed_lanes.filter((k) => k !== kind),
    );

  const addDomain = () => {
    const domain = newDomain.trim();
    if (!domain || draft.chatbot_unsupported_domains.includes(domain)) return;
    set('chatbot_unsupported_domains', [...draft.chatbot_unsupported_domains, domain]);
    setNewDomain('');
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Lanes the CRM answers</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 py-5 sm:grid-cols-2">
          {lanes.map((lane) => (
            <div key={lane.kind} className="flex items-center gap-2.5">
              <Checkbox
                id={`chatbot-lane-${lane.kind}`}
                checked={draft.chatbot_completed_lanes.includes(lane.kind)}
                disabled={!lane.built}
                onCheckedChange={(checked) => toggleLane(lane.kind, checked === true)}
              />
              <Label
                htmlFor={`chatbot-lane-${lane.kind}`}
                className="font-normal cursor-pointer truncate"
                title={lane.kind}
              >
                {lane.kind}
              </Label>
              {lane.built ? null : (
                <span className="text-xs text-muted-foreground shrink-0">Not built</span>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Switches</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 py-5">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="chatbot-stock-denial" className="font-normal cursor-pointer">
              Stock denial lanes
            </Label>
            <Switch
              id="chatbot-stock-denial"
              checked={draft.chatbot_stock_denial_enabled}
              onCheckedChange={(next) => set('chatbot_stock_denial_enabled', next === true)}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="chatbot-business-lane" className="font-normal cursor-pointer">
              Business lane
            </Label>
            <Switch
              id="chatbot-business-lane"
              checked={draft.chatbot_business_lane_enabled}
              onCheckedChange={(next) => set('chatbot_business_lane_enabled', next === true)}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="chatbot-ordering" className="font-normal cursor-pointer">
              Ordering
            </Label>
            <Switch
              id="chatbot-ordering"
              checked={draft.chatbot_ordering_enabled}
              // Turning it ON is confirmed, turning it off is not: switching it on
              // retires the n8n tail, and a turn on a lane the CRM cannot finish then
              // has nobody left to answer it.
              onCheckedChange={(next) => {
                if (next === true) setOrderingConfirmOpen(true);
                else set('chatbot_ordering_enabled', false);
              }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Domains the bot does not answer</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 py-5">
          {draft.chatbot_unsupported_domains.length === 0 ? (
            <p className="text-sm text-muted-foreground">No domains are refused.</p>
          ) : (
            <ul className="space-y-2">
              {draft.chatbot_unsupported_domains.map((domain) => (
                <li
                  key={domain}
                  className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
                >
                  <span className="truncate text-sm" title={domain}>
                    {domain}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove ${domain}`}
                    onClick={() =>
                      set(
                        'chatbot_unsupported_domains',
                        draft.chatbot_unsupported_domains.filter((d) => d !== domain),
                      )
                    }
                  >
                    <XIcon />
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-col gap-3 sm:flex-row">
            <Input
              id="chatbot-new-domain"
              aria-label="Domain to refuse"
              placeholder="goods_receive"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addDomain();
                }
              }}
            />
            <Button type="button" variant="outline" onClick={addDomain}>
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          disabled={save.isPending}
          onClick={() => settingsQuery.data && setDraft(settingsQuery.data)}
        >
          Reset
        </Button>
        <Button
          type="button"
          disabled={save.isPending}
          onClick={() =>
            save.mutate(draft, {
              // Re-seed from what came back, not from what was typed: the row the
              // backend returns is what was actually persisted.
              onSuccess: (saved) => setDraft(saved),
            })
          }
        >
          {save.isPending ? <LoaderCircleIcon className="animate-spin" /> : null}
          Save
        </Button>
      </div>

      <AlertDialog open={orderingConfirmOpen} onOpenChange={setOrderingConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            {/* The title deliberately does not repeat the switch's own label: Radix
                points the dialog's `aria-labelledby` at it, so a title carrying the
                same words would make the switch and the dialog answer to one query. */}
            <AlertDialogTitle>Let the CRM finish every turn?</AlertDialogTitle>
            <AlertDialogDescription>
              Each call to /complete then answers 410, so any lane still switched off has
              nobody left to answer it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => set('chatbot_ordering_enabled', true)}>
              Turn it on
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
