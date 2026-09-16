'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import type { ChatbotMemorySettings } from '../services/chatbotSettingsService';

const RETENTION_OPTIONS = [30, 90, 180, 365].map((days) => ({
  value: String(days),
  label: `${days} days`,
}));

const PROFILE_FIELD_OPTIONS = [
  { value: 'tier', label: 'Tier' },
  { value: 'language', label: 'Language' },
  { value: 'default_ledgers', label: 'Default ledgers' },
];

const FOCUS_RESET_OPTIONS = [
  { value: 'topic_switch', label: 'Topic switch' },
  { value: 'conversation_close', label: 'Conversation close' },
];

/**
 * Settings > Chatbot > Memory card (chatbot turn re-architecture, AC-1513, AC-1561, S5).
 *
 * Backed by `system_settings.chatbot_memory` - one JSONB, four sub-keys. CONTROLLED:
 * the page owns the draft and the ONE Save button (browser pass 1, 16 Sep 2026: a
 * Save of its own here sat right under the Switches card and silently no-op'd the
 * switches), so this card only renders and reports edits.
 */
export default function MemorySettingsCard({
  value,
  onChange,
  isLoading,
  isError,
}: {
  value: ChatbotMemorySettings | null;
  onChange: (next: ChatbotMemorySettings) => void;
  isLoading: boolean;
  isError: boolean;
}) {
  const draft = value;
  const set = <K extends keyof ChatbotMemorySettings>(key: K, v: ChatbotMemorySettings[K]) =>
    draft && onChange({ ...draft, [key]: v });

  if (isError && !draft) {
    return (
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Memory</CardTitle>
        </CardHeader>
        <CardContent className="py-5">
          <p className="text-sm text-destructive">
            Memory settings could not be loaded. Reload the page to try again.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isLoading || !draft) {
    return <Skeleton className="h-56 w-full" />;
  }

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Memory</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 py-5">
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor="chatbot-recall-default" className="cursor-pointer font-normal">
            Episode recall
          </Label>
          <Switch
            id="chatbot-recall-default"
            checked={draft.recall_default}
            onCheckedChange={(v) => set('recall_default', v === true)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Keep episodes for</Label>
          <SearchableSelect
            value={String(draft.episode_retention_days)}
            onChange={(v) => set('episode_retention_days', Number(v))}
            options={RETENTION_OPTIONS}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Profile fields</Label>
          <SearchableMultiSelect
            value={draft.profile_fields}
            onChange={(v) => set('profile_fields', v)}
            options={PROFILE_FIELD_OPTIONS}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Focus reset on</Label>
          <SearchableMultiSelect
            value={draft.focus_reset_events}
            onChange={(v) => set('focus_reset_events', v)}
            options={FOCUS_RESET_OPTIONS}
          />
        </div>
      </CardContent>
    </Card>
  );
}
