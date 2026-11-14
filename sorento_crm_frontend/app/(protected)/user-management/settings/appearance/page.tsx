'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { apiError } from '@/lib/api-client';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { contrastRatio } from '@/lib/theme/contrast';
import { generateTheme, type Theme } from '@/lib/theme/generate';
import { PRESETS, type PresetId } from '@/lib/theme/presets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useSettings } from '../components/settings-context';

const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const DEFAULT_PRESET: PresetId = 'sorento-blue';
const AA = 4.5;

function Preview({ label, mode, theme }: { label: string; mode: 'light' | 'dark'; theme: Theme }) {
  const { tokens, background } = theme;
  return (
    <div
      role="group"
      aria-label={label}
      className={cn('flex min-w-0 flex-col gap-3 rounded-lg border p-4 text-foreground', mode === 'dark' && 'dark')}
      style={{ background }}
    >
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="inline-flex h-8.5 items-center rounded-md px-3 text-sm font-medium"
          style={{ background: tokens.primary, color: tokens['primary-foreground'] }}
        >
          Preview button
        </button>
        <span
          className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
          style={{ background: tokens['primary-soft'], color: tokens.primary }}
        >
          Preview badge
        </span>
      </div>
      <div
        className="rounded-md px-3 py-2 text-sm"
        style={{ background: tokens['primary-soft'], color: tokens.primary }}
      >
        Preview row
      </div>
    </div>
  );
}

export default function AppearancePage() {
  const { settings } = useSettings();
  const queryClient = useQueryClient();

  const saved = settings.theme;
  const [preset, setPreset] = useState<PresetId>(saved?.preset ?? DEFAULT_PRESET);
  const [custom, setCustom] = useState<string>(saved?.customHex ?? '');

  const customValid = HEX_RE.test(custom);
  const customTyped = custom !== '';
  const draftHex = customValid
    ? custom.toLowerCase()
    : (PRESETS.find((p) => p.id === preset) ?? PRESETS[0]).hex;

  const light = generateTheme(draftHex, 'light');
  const dark = generateTheme(draftHex, 'dark');
  const ratio = contrastRatio(light.tokens['primary-foreground'], light.tokens.primary);
  const passes = ratio >= AA;

  const mutation = useMutation({
    mutationFn: async () => {
      const response = await apiFetch('/api/user-management/settings/general', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: { preset, custom_hex: customValid ? custom.toLowerCase() : null } }),
      });
      if (!response.ok) throw await apiError(response, 'Could not save the brand colour');
      return response;
    },
    onSuccess: () => {
      toast.success('Brand colour saved');
      void queryClient.invalidateQueries({ queryKey: ['system-settings'] });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Could not save the brand colour');
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <div role="radiogroup" aria-label="Brand colour" className="flex flex-wrap gap-2">
            {PRESETS.map((p) => {
              const checked = !customTyped && preset === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  aria-label={p.label}
                  title={p.label}
                  onClick={() => {
                    setPreset(p.id);
                    setCustom('');
                  }}
                  className={cn(
                    'inline-flex size-10 items-center justify-center rounded-full border-2 pointer-coarse:size-11',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                    checked ? 'border-foreground' : 'border-transparent',
                  )}
                >
                  <span className="size-7 rounded-full border" style={{ background: p.hex }} />
                </button>
              );
            })}
          </div>
          <div className="flex max-w-xs flex-col gap-1.5">
            <Input
              aria-label="Custom colour"
              placeholder="#rrggbb"
              value={custom}
              aria-invalid={customTyped && !customValid ? true : undefined}
              onChange={(e) => setCustom(e.target.value.trim())}
            />
          </div>
          <p className={cn('text-sm', passes ? 'text-muted-foreground' : 'text-destructive')}>
            {`Button text ${ratio.toFixed(1)}:1, ${passes ? 'passes' : 'fails'}`}
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Preview label="Light preview" mode="light" theme={light} />
          <Preview label="Dark preview" mode="dark" theme={dark} />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={(customTyped && !customValid) || mutation.isPending} onClick={() => mutation.mutate()}>
            Save
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setPreset(DEFAULT_PRESET);
              setCustom('');
            }}
          >
            Reset to Sorento Blue
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
