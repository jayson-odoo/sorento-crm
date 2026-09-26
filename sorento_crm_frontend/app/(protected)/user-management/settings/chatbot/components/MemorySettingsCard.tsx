'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { ChatbotMemorySettings } from '../services/chatbotSettingsService';

const LEVEL_OPTIONS = [
  { value: 'conversation', label: 'This conversation' },
  { value: 'past', label: 'Past conversations' },
  { value: 'full', label: 'Full memory' },
];

/**
 * Settings > Chatbot > Memory card (chatbot memory lane A, round 3 mockup
 * `chatbot-memory-27sep-mockup-settings.html`).
 *
 * Backed by `system_settings.chatbot_memory`, now exactly `{enabled, default_level,
 * own_level_count}` (contract section 2/5). The four dead settings this card used to
 * carry (recall default, keep episodes for, profile fields, focus reset on) are gone -
 * the mockup's own note: "the four old settings nothing read... are gone".
 *
 * CONTROLLED, same as before the S5 chatbot turn re-architecture landed it: the page
 * owns the draft and the ONE Save button, so this card only renders and reports edits.
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
          <Label htmlFor="chatbot-memory-enabled" className="cursor-pointer font-normal">
            Memory for all contacts
          </Label>
          <Switch
            id="chatbot-memory-enabled"
            checked={draft.enabled}
            onCheckedChange={(v) => set('enabled', v === true)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Default context level</Label>
          {/* Never clearable - the level always has a value once memory is on
              (contract section 2: `default_level` is never `off`, never null). */}
          <SearchableSelect
            value={draft.default_level}
            onChange={(v) => set('default_level', v as ChatbotMemorySettings['default_level'])}
            options={LEVEL_OPTIONS}
          />
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label className="font-normal">Contacts with their own level</Label>
          {/* No filter on the Contacts list keys "own chatbot memory level" yet
              (Phase 1) - a plain link until Phase 2 adds one. */}
          <Link href="/user-management/contacts" className="text-sm text-primary hover:underline">
            {draft.own_level_count} contact{draft.own_level_count === 1 ? '' : 's'}
          </Link>
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label className="font-normal">Conversations kept</Label>
          <span className="text-sm text-muted-foreground">Newest 20 per contact</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <Label className="font-normal">Facts kept</Label>
          <span className="text-sm text-muted-foreground">
            Until replaced, removed by staff, or the contact is deleted
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
