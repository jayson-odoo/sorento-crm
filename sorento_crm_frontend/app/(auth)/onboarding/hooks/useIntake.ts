'use client';

/**
 * The public intake screen's hooks layer.
 *
 * Layering: UI -> these hooks -> `lib/onboarding-client` -> backend. Nothing in
 * the component talks to `fetch`, and every error message is the sentence the
 * server sent (the client already unwraps it).
 *
 * The token is the whole auth story here, so it is threaded through explicitly
 * rather than read from storage: a token cached from a previous batch would
 * answer for the wrong request.
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import type { OnboardingIntakeContext } from '@/components/common/onboarding/types';
import {
  fetchIntakeContext,
  saveRows,
  submitIntake,
  type OnboardingDraftRow,
} from '../lib/onboarding-client';

/** Everything the page is handed for its whole session. */
export function useIntakeContext(token: string) {
  return useQuery({
    queryKey: ['onboarding-intake', token],
    queryFn: () => fetchIntakeContext(token),
    retry: false,
  });
}

/**
 * Save the rows without sealing the batch.
 *
 * The link is multi-use until submission (UAC AC-3.2) and the intake email says
 * so, but until this existed the only call to `saveRows` was the one submit made
 * on its way out - so a requester who gathered her list over two days closed the
 * tab and lost it. Saving is explicit rather than automatic: her rows are what
 * she typed, and a background write is not something she asked for.
 */
export function useSaveDraft(
  token: string,
  options: {
    onSuccess: () => void;
    onError: (error: Error) => void;
  },
) {
  return useMutation({
    mutationFn: (rows: OnboardingDraftRow[]) => saveRows(token, rows),
    onSuccess: options.onSuccess,
    onError: options.onError,
  });
}

/**
 * Save then submit, in that order and as one action: the rows have to reach the
 * server before the batch can be sealed, and a submit that raced the save would
 * seal an empty one.
 */
export function useSubmitIntake(
  token: string,
  options: {
    onSuccess: (result: OnboardingIntakeContext) => void;
    onError: (error: Error) => void;
  },
) {
  return useMutation({
    mutationFn: async ({ rows, note }: { rows: OnboardingDraftRow[]; note: string | null }) => {
      await saveRows(token, rows);
      return submitIntake(token, note);
    },
    onSuccess: options.onSuccess,
    onError: options.onError,
  });
}
