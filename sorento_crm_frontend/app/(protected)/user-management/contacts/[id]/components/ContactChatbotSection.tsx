'use client';

import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useContactChatbotProfile, useSaveContactChatbotProfile } from '../hooks/useContactChatbot';

const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'ms', label: 'Bahasa Malaysia' },
  { value: 'zh', label: 'Chinese' },
];

/**
 * Contact Details -> Access -> Chatbot (chatbot turn re-architecture, S1, AC-1515).
 *
 * Recall and language are edited here directly. Tier is read-only once a WhatsApp
 * pick has set it - the Profile shelf's writer is "explicit picks" (PLAN "Design >
 * State"), and a value the contact already picked in a conversation is not
 * overwritten from this card without knowing what that changes downstream.
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
          onCheckedChange={(checked) =>
            save.mutate({ recall_enabled: checked === true, language: profile.language })
          }
        />
      </div>

      <div className="space-y-1.5">
        <Label>Language</Label>
        <SearchableSelect
          value={profile.language ?? ''}
          onChange={(v) =>
            save.mutate({ recall_enabled: profile.recall_enabled, language: v || null })
          }
          clearable
          disabled={save.isPending}
          placeholder="(none)"
          options={LANGUAGE_OPTIONS}
        />
      </div>

      <div className="space-y-1.5">
        <Label>Tier</Label>
        {profile.tier ? (
          <div className="flex items-center gap-2">
            <Badge variant="secondary" appearance="light" size="sm">
              {profile.tier}
            </Badge>
            <span className="text-xs text-muted-foreground">
              Set by a pick{profile.tier_set_at ? `, ${formatDateTimeInMalaysia(profile.tier_set_at)}` : ''}
            </span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Not set yet - answered on the next pick.</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label>Ledgers</Label>
        <p className="text-sm text-muted-foreground">{profile.ledgers_summary}</p>
      </div>
    </div>
  );
}
