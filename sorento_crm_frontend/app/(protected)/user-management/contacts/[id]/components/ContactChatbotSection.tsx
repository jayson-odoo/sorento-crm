'use client';

import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useContactChatbotProfile, useSaveContactChatbotProfile } from '../hooks/useContactChatbot';

const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'ms', label: 'Bahasa Malaysia' },
  { value: 'zh', label: 'Chinese' },
];

const TIER_OPTIONS = [
  { value: 'dealer', label: 'Dealer' },
  { value: 'office', label: 'Office' },
  { value: 'end_user', label: 'End user' },
];

/**
 * Contact Details -> Access -> Chatbot (chatbot turn re-architecture, S5, AC-1515).
 *
 * Recall, tier and language are all edited directly here. The mocked S1 idea of a
 * read-only tier "once a pick set it" has no backend signal to key off (the contact's
 * `chatbot_profile.tier` carries no record of who last set it), so tier is a plain
 * field like language.
 */
export default function ContactChatbotSection({ contactId }: { contactId: string }) {
  const { data: profile, isLoading, isError } = useContactChatbotProfile(contactId);
  const save = useSaveContactChatbotProfile(contactId);

  if (isLoading) {
    return <Skeleton className="h-40 w-full" />;
  }

  if (isError || !profile) {
    return (
      <p className="text-sm text-destructive">
        This contact&apos;s chatbot settings could not be loaded. Reload the page to try again.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="contact-chatbot-recall" className="cursor-pointer font-normal">
          Episode recall
        </Label>
        <Switch
          id="contact-chatbot-recall"
          checked={profile.recall_enabled}
          disabled={save.isPending}
          onCheckedChange={(checked) => save.mutate({ ...profile, recall_enabled: checked === true })}
        />
      </div>

      <div className="space-y-1.5">
        <Label>Language</Label>
        <SearchableSelect
          value={profile.language ?? ''}
          onChange={(v) => save.mutate({ ...profile, language: v || null })}
          clearable
          disabled={save.isPending}
          placeholder="(none)"
          options={LANGUAGE_OPTIONS}
        />
      </div>

      <div className="space-y-1.5">
        <Label>Tier</Label>
        <SearchableSelect
          value={profile.tier ?? ''}
          onChange={(v) => save.mutate({ ...profile, tier: v || null })}
          clearable
          disabled={save.isPending}
          placeholder="(none) - answered on the next pick"
          options={TIER_OPTIONS}
        />
      </div>
    </div>
  );
}
