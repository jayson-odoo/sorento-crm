'use client';

import { useState } from 'react';

import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { SpecProposalReview } from '@/components/spec-proposals';
import { useSpecExtraction } from '../../hooks/useSpecExtraction';

/**
 * One box and one button, where the stored flyer card used to be.
 *
 * The card was a second source of truth: a copy of a printed document kept beside the
 * specifications it produced, which somebody then had to keep in sync with a flyer
 * that had already been reprinted. What a person actually holds is a piece of text -
 * a flyer card, a leaflet paragraph, a line from a supplier - and what they want from
 * it is the specifications, not a stored copy of the text.
 *
 * So the text is never persisted (AC-B.1). It lives in this component's state and in
 * the request body, and it is gone the moment this unmounts. What survives is the
 * values a person accepted, each carrying the words it was read from.
 *
 * The review itself is `components/spec-proposals`, shared with milestone 2's
 * supplier acceptance, so this file holds the panel's states and nothing else.
 */

export default function SpecExtractPanel({
  productId,
  productCode,
  canEdit,
  valueLabels,
}: {
  productId: string;
  productCode: string;
  canEdit: boolean;
  /** `{spec_key: value_labels}` (E.2), from the registry the tab already loaded. */
  valueLabels?: Record<string, Record<string, string>>;
}) {
  /** Component state only. Nothing reads it back and nothing stores it. */
  const [text, setText] = useState('');
  const extraction = useSpecExtraction(productId, productCode);
  const { result, proposals, selectedKeys, isExtracting, isApplying, error } =
    extraction;

  // Nothing here is readable without the write: the panel IS the control, so a user
  // who cannot write gets no affordance that would 403 at submit - the same rule the
  // table's own edit affordances follow.
  if (!canEdit) return null;

  const busy = isExtracting || isApplying;

  const read = async () => {
    if (!text.trim() || busy) return;
    await extraction.extract(text);
  };

  const apply = async () => {
    const applied = await extraction.apply();
    // Only on success: a failed write leaves the text and the ticks exactly as they
    // were, because retyping a flyer card is the one thing this screen exists to stop.
    if (applied) setText('');
  };

  return (
    <div className="flex flex-col gap-3" data-spec-extract-panel>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        Read specs from a text
      </div>

      <Textarea
        className="min-h-[6rem] font-mono"
        value={text}
        disabled={busy}
        placeholder="Paste a flyer card, a leaflet paragraph, or a supplier line"
        onChange={(event) => setText(event.target.value)}
        aria-label="Text to read specifications from"
        data-spec-extract-input
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={read} disabled={!text.trim() || busy}>
          {isExtracting ? 'Reading…' : 'Read specs from this'}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertIcon />
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}

      {result && (
        <div className="flex flex-col gap-3">
          {/* One short line, not a warning: the answer is still an answer, it was
              just read by the rules alone. */}
          {result.engine === 'deterministic' && (
            <p
              className="text-sm text-muted-foreground"
              data-spec-extract-degraded
            >
              Read by the rules only - no model was reachable.
            </p>
          )}

          {proposals.length === 0 ? (
            <div
              className="rounded-md border border-dashed p-4 text-center"
              data-spec-extract-empty
            >
              {/* Two different answers, and saying the first one for both is a
                  claim the reading never made: "0 values it states are already
                  stored" reads as if the text WAS understood and merely agreed
                  with the product. Nothing was recognised at all. */}
              <p className="text-sm font-medium text-foreground">
                {result.unchanged === 0
                  ? 'Nothing recognisable in this text'
                  : 'Nothing new in this text'}
              </p>
              {result.unchanged > 0 && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {result.unchanged === 1
                    ? '1 value it states is already stored.'
                    : `${result.unchanged} values it states are already stored.`}
                </p>
              )}
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={extraction.discard}
              >
                Discard
              </Button>
            </div>
          ) : (
            <>
              <SpecProposalReview
                proposals={proposals}
                selectedKeys={selectedKeys}
                onSelectionChange={extraction.setSelectedKeys}
                disabled={isApplying}
                valueLabels={valueLabels}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  onClick={apply}
                  disabled={selectedKeys.length === 0 || isApplying}
                  data-spec-extract-apply
                >
                  {isApplying ? 'Applying…' : `Apply ${selectedKeys.length}`}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={extraction.discard}
                  disabled={isApplying}
                >
                  Discard
                </Button>
                {result.unchanged > 0 && (
                  <span className="text-sm text-muted-foreground">
                    {result.unchanged === 1
                      ? '1 value it states is already stored.'
                      : `${result.unchanged} values it states are already stored.`}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
