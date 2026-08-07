'use client';

import { useState } from 'react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { updateSpecKey } from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';

/**
 * Edit one spec key.
 *
 * The seed/user split is surfaced rather than hidden. A shipped key's values are the
 * chatbot parser's contract — renaming one here would break the two apart silently —
 * so the editor offers the two things that are genuinely safe: extra words customers
 * say, and how heavily the key counts. Anything it will not let you change, it says
 * why rather than greying out a control with no explanation.
 */
export default function SpecKeyEditor({
  specKey,
  onSaved,
  onCancel,
}: {
  specKey: SpecRegistryKey;
  onSaved: (updated: SpecRegistryKey) => void;
  onCancel: () => void;
}) {
  const isSeed = specKey.source === 'seed';
  const values = specKey.allowed_values.length > 0 ? specKey.allowed_values : ['true'];

  const [label, setLabel] = useState(specKey.label);
  const [weight, setWeight] = useState(String(specKey.rank_weight ?? 1));
  const [tolerance, setTolerance] = useState(String(specKey.match_tolerance ?? 0));
  const [decay, setDecay] = useState(String(specKey.match_decay ?? 0));
  const [active, setActive] = useState(specKey.is_active);
  const [userWords, setUserWords] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      values.map((v) => [v, (specKey.user_synonyms?.[v] ?? []).join(', ')]),
    ),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const synonyms: Record<string, string[]> = {};
      for (const [value, raw] of Object.entries(userWords)) {
        const words = raw
          .split(',')
          .map((w) => w.trim())
          .filter(Boolean);
        if (words.length > 0) synonyms[value] = words;
      }
      onSaved(
        await updateSpecKey(specKey.spec_key, {
          label,
          rank_weight: Number(weight),
          is_active: active,
          match_tolerance: Number(tolerance),
          match_decay: Number(decay),
          user_synonyms: synonyms,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-md border bg-muted/20 p-4">
      {error && (
        <Alert variant="destructive">
          <AlertIcon />
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}

      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-[12rem] flex-1">
          <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
            What staff call it
          </label>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="w-28">
          <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
            Weight
          </label>
          <Input
            type="number"
            step="0.5"
            min="0"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
          />
        </div>
        {specKey.data_type === 'numeric' && (
          <>
            <div className="w-32">
              <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
                Exact within
              </label>
              <Input
                type="number"
                step="1"
                min="0"
                value={tolerance}
                onChange={(e) => setTolerance(e.target.value)}
              />
            </div>
            <div className="w-32">
              <label className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block">
                No match beyond
              </label>
              <Input
                type="number"
                step="10"
                min="0"
                value={decay}
                onChange={(e) => setDecay(e.target.value)}
              />
            </div>
          </>
        )}
        <label className="flex items-center gap-2 text-sm pb-2">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          In use
        </label>
      </div>

      {specKey.data_type === 'numeric' && (
        <p className="text-xs text-muted-foreground">
          A measurement counts as an exact match within{' '}
          <span className="font-mono">{tolerance || 0}</span>
          {specKey.unit ? ` ${specKey.unit}` : ''}, and stops counting at{' '}
          <span className="font-mono">{decay || 0}</span>. Set “no match beyond” to 0 for
          a count — one bowl and two bowls are not nearly the same thing.
        </p>
      )}

      <div className="flex flex-col gap-2">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Extra words customers say
        </div>
        {values.map((value) => (
          <div key={value} className="flex flex-wrap items-center gap-2">
            <span className="w-40 shrink-0 font-mono text-sm">
              {value === 'true' && specKey.data_type === 'boolean' ? 'when true' : value}
            </span>
            <Input
              className="min-w-[14rem] flex-1"
              placeholder="comma separated"
              value={userWords[value] ?? ''}
              onChange={(e) =>
                setUserWords((current) => ({ ...current, [value]: e.target.value }))
              }
            />
            <div className="flex flex-wrap gap-1">
              {(specKey.synonyms?.[value] ?? [])
                .filter((w) => !(specKey.user_synonyms?.[value] ?? []).includes(w))
                .map((word) => (
                  <Badge key={word} variant="outline" size="sm">
                    {word}
                  </Badge>
                ))}
            </div>
          </div>
        ))}
        <p className="text-xs text-muted-foreground">
          Your words are <strong>added to</strong> the ones shown as chips, never
          replacing them
          {isSeed
            ? ' — those ship with the product and the chatbot relies on them.'
            : '.'}
        </p>
      </div>

      <div className="flex gap-2">
        <Button onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
