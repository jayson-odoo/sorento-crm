'use client';

import * as React from 'react';
import { NonCancellableOverrideDialog } from '../components/NonCancellableOverrideDialog';
import { isOverridableRefusal } from '../lib/nonCancellable';
import type { NonCancellableRefusal } from '../types/project.types';

/**
 * Run a call; when the server refuses it with an overridable `non_cancellable_line`, ask for a
 * reason and run it again with that reason.
 *
 * `run` is a mutation's `mutateAsync` (its own `onError` already toasts every other failure and
 * skips the overridable refusal). `attempt` resolves quietly on any failure; the dialog stays
 * open on a failed retry so the reason is not lost.
 */
export function useNonCancellableOverride<V>(
  run: (vars: V, overrideReason?: string) => Promise<unknown>,
) {
  const [held, setHeld] = React.useState<{ vars: V; refusal: NonCancellableRefusal } | null>(
    null,
  );
  const [submitting, setSubmitting] = React.useState(false);

  const attempt = React.useCallback(
    async (vars: V) => {
      try {
        await run(vars);
      } catch (error) {
        if (isOverridableRefusal(error)) setHeld({ vars, refusal: error.details });
      }
    },
    [run],
  );

  const override = async (reason: string) => {
    if (!held) return;
    setSubmitting(true);
    try {
      await run(held.vars, reason);
      setHeld(null);
    } catch {
      // The mutation's onError has said why; the dialog stays for another go.
    } finally {
      setSubmitting(false);
    }
  };

  const dialog = held ? (
    <NonCancellableOverrideDialog
      refusal={held.refusal}
      submitting={submitting}
      onOverride={override}
      onCancel={() => setHeld(null)}
    />
  ) : null;

  return { attempt, dialog };
}
