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
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';

import { useChatbotSettings, useSaveChatbotSettings } from './hooks/useChatbotSettings';
import {
  useChatbotMemorySettings,
  useChatbotTierOrder,
  useSaveChatbotMemorySettings,
  useSaveChatbotTierOrder,
} from './hooks/useChatbotMemoryAndTierOrder';
import type { ChatbotMemorySettings, ChatbotSettings } from './services/chatbotSettingsService';
import MemorySettingsCard from './components/MemorySettingsCard';
import TierOrderCard from './components/TierOrderCard';
import CrossDomainLadderCard from './components/CrossDomainLadderCard';

/**
 * Settings -> Chatbot (AC-809, AC-810; chatbot turn re-architecture S1/S5, AC-1513,
 * AC-1560).
 *
 * The three switches that used to be environment flags - read per turn by the engine,
 * so a change here takes effect on the next WhatsApp message with no deploy. The
 * domains the bot refuses used to be a free-text list here (AC-931); that box is
 * retired - "Supported" now lives on each domain's own row on the Chatbot Domains page,
 * which is also where a domain's tools, narrowing and escalation team live, so a
 * refusal is no longer a name typed twice.
 *
 * The "Lanes the CRM answers" card is retired (S3 ruling, 16 Sep 2026):
 * `chatbot_completed_lanes` no longer gates which turns the CRM finishes now that the
 * turn engine itself decides, so a checkbox here would no longer change anything the
 * next WhatsApp message does.
 */

export default function ChatbotSettingsPage() {
  const settingsQuery = useChatbotSettings();
  const save = useSaveChatbotSettings();
  // One Save for the whole page (browser pass 1, 16 Sep 2026): the Memory and Tier
  // order cards used to carry a Save each, right under a Switches card that had none
  // of its own - so the nearest Save silently no-op'd the switches. The page owns all
  // three drafts now and the one button fires every PUT that has something to save.
  const memoryQuery = useChatbotMemorySettings();
  const saveMemory = useSaveChatbotMemorySettings();
  const tierOrderQuery = useChatbotTierOrder();
  const saveTierOrder = useSaveChatbotTierOrder();

  const [draft, setDraft] = useState<ChatbotSettings | null>(null);
  const [memoryDraft, setMemoryDraft] = useState<ChatbotMemorySettings | null>(null);
  const [tierOrderDraft, setTierOrderDraft] = useState<string[] | null>(null);
  const [orderingConfirmOpen, setOrderingConfirmOpen] = useState(false);

  useEffect(() => {
    if (settingsQuery.data && draft === null) setDraft(settingsQuery.data);
  }, [settingsQuery.data, draft]);
  useEffect(() => {
    if (memoryQuery.data && memoryDraft === null) setMemoryDraft(memoryQuery.data);
  }, [memoryQuery.data, memoryDraft]);
  useEffect(() => {
    if (tierOrderQuery.data && tierOrderDraft === null) setTierOrderDraft(tierOrderQuery.data);
  }, [tierOrderQuery.data, tierOrderDraft]);

  const saving = save.isPending || saveMemory.isPending || saveTierOrder.isPending;

  // The failed load is checked FIRST. A load that fails leaves `draft` null, so a
  // loading check that also covered `!draft` would win every time and the operator
  // would wait on skeletons that never resolve.
  if (settingsQuery.isError && !draft) {
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

  if (settingsQuery.isLoading || !draft) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const set = <K extends keyof ChatbotSettings>(key: K, value: ChatbotSettings[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  return (
    <div className="space-y-5">
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

      <MemorySettingsCard
        value={memoryDraft}
        onChange={setMemoryDraft}
        isLoading={memoryQuery.isLoading}
        isError={memoryQuery.isError}
      />
      <TierOrderCard
        value={tierOrderDraft}
        onChange={setTierOrderDraft}
        isLoading={tierOrderQuery.isLoading}
        isError={tierOrderQuery.isError}
      />
      <CrossDomainLadderCard />

      <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          disabled={saving}
          onClick={() => {
            if (settingsQuery.data) setDraft(settingsQuery.data);
            if (memoryQuery.data) setMemoryDraft(memoryQuery.data);
            if (tierOrderQuery.data) setTierOrderDraft(tierOrderQuery.data);
          }}
        >
          Reset
        </Button>
        <Button
          type="button"
          disabled={saving}
          onClick={() => {
            // Re-seed each draft from what came back, not from what was typed: the
            // row the backend returns is what was actually persisted.
            save.mutate(draft, { onSuccess: (saved) => setDraft(saved) });
            if (memoryDraft) {
              saveMemory.mutate(memoryDraft, { onSuccess: (saved) => setMemoryDraft(saved) });
            }
            if (tierOrderDraft) {
              saveTierOrder.mutate(tierOrderDraft, {
                onSuccess: (saved) => setTierOrderDraft(saved),
              });
            }
          }}
        >
          {saving ? <LoaderCircleIcon className="animate-spin" /> : null}
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
