'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
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
 * Settings > Chatbot > Memory card (chatbot turn re-architecture, AC-1513, M5).
 *
 * Backed by `system_settings.chatbot_memory` (S5, AC-1561), one JSONB with these four
 * sub-keys - a single decision made on one card, not four columns. Controlled: the
 * page's own draft carries the value, saved by the page's single Save button.
 */
export default function MemorySettingsCard({
  value,
  onChange,
}: {
  value: ChatbotMemorySettings;
  onChange: (next: ChatbotMemorySettings) => void;
}) {
  const set = <K extends keyof ChatbotMemorySettings>(key: K, next: ChatbotMemorySettings[K]) =>
    onChange({ ...value, [key]: next });

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
            checked={value.recall_default}
            onCheckedChange={(v) => set('recall_default', v === true)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Keep episodes for</Label>
          <SearchableSelect
            value={String(value.episode_retention_days)}
            onChange={(v) => set('episode_retention_days', Number(v))}
            options={RETENTION_OPTIONS}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Profile fields</Label>
          <SearchableMultiSelect
            value={value.profile_fields}
            onChange={(v) => set('profile_fields', v)}
            options={PROFILE_FIELD_OPTIONS}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Focus reset on</Label>
          <SearchableMultiSelect
            value={value.focus_reset_events}
            onChange={(v) => set('focus_reset_events', v)}
            options={FOCUS_RESET_OPTIONS}
          />
        </div>
      </CardContent>
    </Card>
  );
}
