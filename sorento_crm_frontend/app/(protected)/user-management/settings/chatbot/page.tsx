'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { RiErrorWarningFill } from '@remixicon/react';
import { LoaderCircleIcon } from 'lucide-react';

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
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';

import { useChatbotLanes, useChatbotSettings, useSaveChatbotSettings } from './hooks/useChatbotSettings';
import type { ChatbotSettings } from './services/chatbotSettingsService';
import MemorySettingsCard from './components/MemorySettingsCard';
import TierOrderCard from './components/TierOrderCard';
import CrossDomainLadderCard from './components/CrossDomainLadderCard';

/**
 * Settings -> Chatbot (AC-809, AC-810; chatbot turn re-architecture S1, AC-1513).
 *
 * Which lanes the CRM finishes and the three switches that used to be environment
 * flags - read per turn by the engine, so a change here takes effect on the next
 * WhatsApp message with no deploy. The domains the bot refuses used to be a
 * free-text list here (AC-931); that box is retired - "Supported" now lives on
 * each domain's own row on the Chatbot Domains page, which is also where a
 * domain's tools, narrowing and escalation team live, so a refusal is no longer a
 * name typed twice.
 */

export default function ChatbotSettingsPage() {
  const lanesQuery = useChatbotLanes();
  const settingsQuery = useChatbotSettings();
  const save = useSaveChatbotSettings();

  const [draft, setDraft] = useState<ChatbotSettings | null>(null);
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

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Lanes the CRM answers</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 py-5 sm:grid-cols-2">
          {lanes.map((lane) => {
            const checked = draft.chatbot_completed_lanes.includes(lane.kind);
            return (
              <div key={lane.kind} className="flex items-center gap-2.5">
                <Checkbox
                  id={`chatbot-lane-${lane.kind}`}
                  checked={checked}
                  // Unbuilt blocks turning one ON, never turning one OFF. A kind listed
                  // while its switch was on and then stranded when it went off would
                  // otherwise be a checkbox nobody can clear, which is a trap rather
                  // than a guard.
                  disabled={!lane.built && !checked}
                  onCheckedChange={(next) => toggleLane(lane.kind, next === true)}
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
            );
          })}
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
        <CardContent className="py-5">
          <p className="text-sm text-muted-foreground">
            Moved to each domain&apos;s own row -{' '}
            <Link
              href="/system-management/chatbot-domains"
              className="text-primary hover:underline"
            >
              Chatbot Domains
            </Link>
            . Turn the Supported switch off there instead of listing the name here.
          </p>
        </CardContent>
      </Card>

      <MemorySettingsCard />
      <TierOrderCard />
      <CrossDomainLadderCard />

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
