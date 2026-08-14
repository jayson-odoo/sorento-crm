'use client';

import { useEffect, useMemo, useState } from 'react';
import { RiErrorWarningFill } from '@remixicon/react';
import { LoaderCircleIcon } from 'lucide-react';

import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { PROVIDER_OPTIONS } from '@/app/(protected)/system-management/ai-assistant/lib/modelOptions';

import {
  useChatbotMediaSettings,
  useSaveChatbotMediaSettings,
} from './hooks/useChatbotMediaSettings';
import type {
  ChatbotMediaSettings,
  MediaLanguageMode,
} from './services/chatbotMediaSettingsService';
import {
  LANGUAGE_MODE_OPTIONS,
  LANGUAGE_OPTIONS,
  TRANSCRIBE_MODEL_OPTIONS,
  imageModelOptions,
  parseCsv,
  toCsv,
} from './lib/chatbot-media-options';

/**
 * Settings -> Chatbot Media (UAC S1-04).
 *
 * Every number the media endpoint enforces is edited here, so changing an allowance
 * or a model is an operator action rather than a deploy. The per-contact gate and
 * any per-contact override live on the contact itself; this page is the default
 * everyone inherits.
 */

/** The draft is all strings, because a half-typed number is a string. */
type Draft = {
  imageMonthlyLimit: string;
  voiceMonthlyLimit: string;
  voiceMaxSeconds: string;
  burstLimit: string;
  burstWindowSeconds: string;
  warnThresholdPercent: string;
  imageProvider: string;
  imageModel: string;
  imageDegradedModel: string;
  transcribeModel: string;
  languageMode: MediaLanguageMode;
  languagePinned: string;
  languageHints: string[];
  syncWaitSeconds: string;
  extractionTimeoutSeconds: string;
  maxEntities: string;
};

function toDraft(settings: ChatbotMediaSettings): Draft {
  return {
    imageMonthlyLimit: String(settings.media_image_monthly_limit),
    voiceMonthlyLimit: String(settings.media_voice_monthly_limit),
    voiceMaxSeconds: String(settings.media_voice_max_seconds),
    burstLimit: String(settings.media_burst_limit),
    burstWindowSeconds: String(settings.media_burst_window_seconds),
    warnThresholdPercent: String(settings.media_warn_threshold_percent),
    imageProvider: settings.media_image_provider ?? '',
    imageModel: settings.media_image_model ?? '',
    imageDegradedModel: settings.media_image_degraded_model ?? '',
    transcribeModel: settings.media_transcribe_model,
    languageMode: settings.media_language_mode,
    languagePinned: settings.media_language_pinned,
    languageHints: parseCsv(settings.media_language_hints),
    syncWaitSeconds: String(settings.media_sync_wait_seconds),
    extractionTimeoutSeconds: String(settings.media_extraction_timeout_seconds),
    maxEntities: String(settings.media_max_entities),
  };
}

function fromDraft(draft: Draft): ChatbotMediaSettings {
  return {
    media_image_monthly_limit: Number(draft.imageMonthlyLimit.trim()),
    media_voice_monthly_limit: Number(draft.voiceMonthlyLimit.trim()),
    media_voice_max_seconds: Number(draft.voiceMaxSeconds.trim()),
    media_burst_limit: Number(draft.burstLimit.trim()),
    media_burst_window_seconds: Number(draft.burstWindowSeconds.trim()),
    media_warn_threshold_percent: Number(draft.warnThresholdPercent.trim()),
    media_image_provider: draft.imageProvider.trim() || null,
    media_image_model: draft.imageModel.trim() || null,
    media_image_degraded_model: draft.imageDegradedModel.trim() || null,
    media_transcribe_model: draft.transcribeModel.trim(),
    media_language_mode: draft.languageMode,
    media_language_pinned: draft.languagePinned.trim(),
    media_language_hints: toCsv(draft.languageHints),
    media_sync_wait_seconds: Number(draft.syncWaitSeconds.trim()),
    media_extraction_timeout_seconds: Number(draft.extractionTimeoutSeconds.trim()),
    media_max_entities: Number(draft.maxEntities.trim()),
  };
}

/**
 * The bounds the backend already enforces on `SystemSettingUpdate`, mirrored per
 * field so every number is refused inline with a sentence rather than coming back
 * as a 422 the operator has to decode. A field validated only for positivity was
 * the odd one out, not the norm.
 */
const NUMBER_BOUNDS = {
  imageMonthlyLimit: [0, 100000],
  voiceMonthlyLimit: [0, 100000],
  voiceMaxSeconds: [1, 3600],
  burstLimit: [0, 1000],
  burstWindowSeconds: [1, 3600],
  warnThresholdPercent: [1, 100],
  syncWaitSeconds: [5, 90],
  extractionTimeoutSeconds: [5, 110],
  maxEntities: [1, 100],
} as const satisfies Record<string, readonly [number, number]>;

type NumberKey = keyof typeof NUMBER_BOUNDS;

function rangeError(raw: string, min: number, max: number): string | undefined {
  const trimmed = raw.trim();
  const message = `Enter a whole number between ${min} and ${max}.`;
  if (!/^\d+$/.test(trimmed)) return message;
  const value = Number(trimmed);
  return value < min || value > max ? message : undefined;
}

/**
 * Every numeric field is bounded, and the two waits are additionally validated
 * against each other because the backend rejects the pair rather than either
 * number on its own: an extraction ceiling below the synchronous wait kills a job
 * at exactly the moment the endpoint degrades to `pending`. Saying so here means
 * the operator reads a sentence rather than decoding a 400 after pressing Save.
 */
function numberErrors(draft: Draft): Partial<Record<NumberKey, string>> {
  const errors: Partial<Record<NumberKey, string>> = {};
  for (const key of Object.keys(NUMBER_BOUNDS) as NumberKey[]) {
    const [min, max] = NUMBER_BOUNDS[key];
    const error = rangeError(draft[key], min, max);
    if (error) errors[key] = error;
  }
  if (!errors.syncWaitSeconds && !errors.extractionTimeoutSeconds) {
    const wait = Number(draft.syncWaitSeconds.trim());
    if (Number(draft.extractionTimeoutSeconds.trim()) < wait) {
      errors.extractionTimeoutSeconds = `Must be at least the synchronous wait of ${wait} seconds, or a job that outlives the wait is killed instead of finishing.`;
    }
  }
  return errors;
}

export default function ChatbotMediaSettingsPage() {
  const settingsQuery = useChatbotMediaSettings();
  const save = useSaveChatbotMediaSettings();
  const [draft, setDraft] = useState<Draft | null>(null);

  useEffect(() => {
    if (settingsQuery.data && draft === null) setDraft(toDraft(settingsQuery.data));
  }, [settingsQuery.data, draft]);

  const numberError = useMemo(
    () => (draft ? numberErrors(draft) : ({} as Partial<Record<NumberKey, string>>)),
    [draft],
  );

  const invalid = useMemo(() => {
    if (!draft) return {} as Record<string, boolean>;
    return {
      transcribeModel: draft.transcribeModel.trim() === '',
      languagePinned: draft.languageMode === 'pinned' && draft.languagePinned.trim() === '',
      languageHints: draft.languageMode === 'hints' && draft.languageHints.length === 0,
    };
  }, [draft]);

  const anyInvalid =
    Object.keys(numberError).length > 0 || Object.values(invalid).some(Boolean);

  // The failed load is checked FIRST. A load that fails leaves `draft` null, so a
  // loading check that also covers `!draft` wins every time and the operator waits
  // on skeletons that never resolve. The `!draft` guard here keeps a failed
  // background refetch from throwing away edits the operator has already made.
  if (settingsQuery.isError && !draft) {
    return (
      <Alert variant="mono" icon="destructive">
        <AlertIcon>
          <RiErrorWarningFill />
        </AlertIcon>
        <AlertTitle>
          Chatbot media settings could not be loaded. Reload the page to try again.
        </AlertTitle>
      </Alert>
    );
  }

  if (settingsQuery.isLoading || !draft) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  const modelOptions = imageModelOptions(draft.imageProvider);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Monthly allowances</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-5 py-5 sm:grid-cols-2">
          <NumberField
            id="media-image-monthly-limit"
            label="Photos per contact per month"
            value={draft.imageMonthlyLimit}
            error={numberError.imageMonthlyLimit}
            onChange={(v) => set('imageMonthlyLimit', v)}
          />
          <NumberField
            id="media-voice-monthly-limit"
            label="Voice notes per contact per month"
            value={draft.voiceMonthlyLimit}
            error={numberError.voiceMonthlyLimit}
            onChange={(v) => set('voiceMonthlyLimit', v)}
          />
          <NumberField
            id="media-voice-max-seconds"
            label="Maximum clip seconds"
            hint="A longer voice note is refused before anything is spent."
            value={draft.voiceMaxSeconds}
            error={numberError.voiceMaxSeconds}
            onChange={(v) => set('voiceMaxSeconds', v)}
          />
          <NumberField
            id="media-warn-threshold"
            label="Warn at percent of allowance"
            hint="The contact is told once per month, per media type."
            value={draft.warnThresholdPercent}
            error={numberError.warnThresholdPercent}
            onChange={(v) => set('warnThresholdPercent', v)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Pacing</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-5 py-5 sm:grid-cols-2">
          <NumberField
            id="media-burst-limit"
            label="Items per burst window"
            hint="0 turns pacing off, so no contact is ever asked to slow down."
            value={draft.burstLimit}
            error={numberError.burstLimit}
            onChange={(v) => set('burstLimit', v)}
          />
          <NumberField
            id="media-burst-window"
            label="Burst window seconds"
            value={draft.burstWindowSeconds}
            error={numberError.burstWindowSeconds}
            onChange={(v) => set('burstWindowSeconds', v)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Image extraction</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 py-5">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="media-image-provider">Provider</Label>
              <SearchableSelect
                id="media-image-provider"
                value={draft.imageProvider}
                onChange={(v) => {
                  set('imageProvider', v);
                  set('imageModel', '');
                }}
                options={PROVIDER_OPTIONS}
                clearable
                placeholder="AI assistant provider"
              />
              <p className="text-xs text-muted-foreground">
                Blank uses whatever the AI assistant is configured with.
              </p>
            </div>
            <ModelField
              id="media-image-model"
              label="Standard model"
              value={draft.imageModel}
              options={modelOptions}
              onChange={(v) => set('imageModel', v)}
              hint="Blank uses the AI assistant model."
            />
            <ModelField
              id="media-image-degraded-model"
              label="Degraded model"
              value={draft.imageDegradedModel}
              options={modelOptions}
              onChange={(v) => set('imageDegradedModel', v)}
              hint="Used once a contact is past their monthly allowance."
            />
            <NumberField
              id="media-max-entities"
              label="Maximum entities per image"
              hint="Beyond this the result is truncated and says so."
              value={draft.maxEntities}
              error={numberError.maxEntities}
              onChange={(v) => set('maxEntities', v)}
            />
            <NumberField
              id="media-sync-wait"
              label="Synchronous wait seconds"
              hint="How long a reply waits for extraction before it returns pending, which is what bounds the per-contact lock."
              value={draft.syncWaitSeconds}
              error={numberError.syncWaitSeconds}
              onChange={(v) => set('syncWaitSeconds', v)}
            />
            <NumberField
              id="media-extraction-timeout"
              label="Extraction timeout seconds"
              hint="Must stay under 120 so a paused turn cannot outlive its lock."
              value={draft.extractionTimeoutSeconds}
              error={numberError.extractionTimeoutSeconds}
              onChange={(v) => set('extractionTimeoutSeconds', v)}
            />
          </div>
          {draft.imageDegradedModel.trim() === '' ? (
            <Alert variant="mono" icon="warning">
              <AlertIcon>
                <RiErrorWarningFill />
              </AlertIcon>
              <AlertTitle>
                No degraded model set, so a contact at their monthly allowance is refused
                instead of continuing at lower accuracy.
              </AlertTitle>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Voice transcription</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-5 py-5 sm:grid-cols-2">
          <ModelField
            id="media-transcribe-model"
            label="Transcription model"
            value={draft.transcribeModel}
            options={TRANSCRIBE_MODEL_OPTIONS}
            onChange={(v) => set('transcribeModel', v)}
            invalid={invalid.transcribeModel}
            required
          />
          <div className="space-y-2">
            <Label htmlFor="media-language-mode">Language strategy</Label>
            <SearchableSelect
              id="media-language-mode"
              value={draft.languageMode}
              onChange={(v) => set('languageMode', (v || 'pinned') as MediaLanguageMode)}
              options={LANGUAGE_MODE_OPTIONS}
              placeholder="Select a strategy"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="media-language-pinned">Pinned language</Label>
            <SearchableSelect
              id="media-language-pinned"
              value={draft.languagePinned}
              onChange={(v) => set('languagePinned', v)}
              options={LANGUAGE_OPTIONS}
              disabled={draft.languageMode !== 'pinned'}
              placeholder="Select a language"
            />
            <p className="text-xs text-muted-foreground">
              Used when the strategy is pinned.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="media-language-hints">Hint languages</Label>
            <SearchableMultiSelect
              value={draft.languageHints}
              onChange={(v) => set('languageHints', v)}
              options={LANGUAGE_OPTIONS}
              disabled={draft.languageMode !== 'hints'}
              placeholder="Select languages"
            />
            <p className="text-xs text-muted-foreground">
              Used when the strategy is a hint list.
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          disabled={save.isPending}
          onClick={() => settingsQuery.data && setDraft(toDraft(settingsQuery.data))}
        >
          Reset
        </Button>
        <Button
          type="button"
          disabled={save.isPending || anyInvalid}
          onClick={() =>
            save.mutate(fromDraft(draft), {
              // Re-seed from what came back, not from what was typed: the row the
              // backend returns is what was actually persisted, so a coerced or
              // rejected-and-left-alone value shows immediately instead of the
              // form drifting away from the database until the next reload.
              onSuccess: (saved) => setDraft(toDraft(saved)),
            })
          }
        >
          {save.isPending ? <LoaderCircleIcon className="animate-spin" /> : null}
          Save Settings
        </Button>
      </div>
    </div>
  );
}

function NumberField({
  id,
  label,
  hint,
  value,
  error,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  /** Shown in place of the hint, so a rejected number says why before it is saved. */
  error?: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="numeric"
        value={value}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {error ? (
        <p id={`${id}-error`} className="text-xs text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

/**
 * A model is picked from the list or typed, the same way the AI assistant model
 * pickers work: the provider ships models faster than the list is updated, so the
 * dropdown offers rather than restricts.
 */
function ModelField({
  id,
  label,
  hint,
  value,
  options,
  invalid,
  required,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  options: SearchableSelectOption[];
  invalid?: boolean;
  required?: boolean;
  onChange: (value: string) => void;
}) {
  const known = options.some((opt) => opt.value === value);
  const merged =
    value && !known ? [...options, { value, label: value }] : options;

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <SearchableSelect
        id={id}
        value={value}
        onChange={onChange}
        options={merged}
        clearable={!required}
        placeholder={required ? 'Select a model' : 'Inherit'}
      />
      <Input
        className="font-mono text-xs"
        placeholder="or type a model name"
        value={value}
        aria-invalid={invalid}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
