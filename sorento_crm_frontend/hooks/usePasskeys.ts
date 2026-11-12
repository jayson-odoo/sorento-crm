/**
 * Passkey queries and mutations (PASSKEY-LOGIN). UI -> these hooks -> services/passkeyService.
 * Removal is not here: it is the deferred record action `user_passkey.delete`
 * (`useDeferredAction`), parked per row.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { signIn } from 'next-auth/react';
import { startAuthentication, startRegistration } from '@simplewebauthn/browser';
import { toast } from '@/lib/toast';
import { isPasskeyPromptCancelled } from '@/lib/passkey';

import {
  fetchMyPasskeys,
  fetchPasskeyRegistrationOptions,
  fetchPasskeySignInOptions,
  fetchPasskeyStatus,
  fetchUserPasskeys,
  registerPasskey,
  renamePasskey,
  sendPasskeyReauthCode,
  setUserPasskeyEnabled,
  type PasskeyItem,
  type PasskeyProof,
} from '@/services/passkeyService';

export const MY_PASSKEYS_KEY = ['auth', 'passkeys'] as const;
export const userPasskeysKey = (userId: string) => ['user-passkeys', userId] as const;

export function usePasskeyStatusQuery(enabled = true) {
  return useQuery<{ enabled: boolean }>({
    queryKey: ['auth', 'passkey-status'],
    queryFn: fetchPasskeyStatus,
    enabled,
  });
}

/**
 * The sign-in ceremony (AC-40 / AC-41): options -> the browser's prompt (or the Email field's
 * autofill) -> NextAuth `passkey` -> `onSignedIn`. A cancelled prompt, or a request whose
 * `signal` was aborted, shows nothing; a refusal reaches `onError` as the backend's message.
 */
export function usePasskeySignIn({
  onSignedIn,
  onError,
}: {
  onSignedIn: () => void | Promise<void>;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const start = useCallback(
    async ({ autofill = false, signal }: { autofill?: boolean; signal?: AbortSignal } = {}) => {
      const live = () => mounted.current && !signal?.aborted;
      try {
        const { challenge_id, options } = await fetchPasskeySignInOptions();
        if (!live()) return;
        const credential = await startAuthentication({
          optionsJSON: options,
          useBrowserAutofill: autofill,
        });
        if (!live()) return;
        setBusy(true);
        const response = await signIn('passkey', {
          redirect: false,
          challengeId: challenge_id,
          credential: JSON.stringify(credential),
        });
        if (!live()) return;
        if (response?.error) {
          let message = response.error;
          try {
            message = JSON.parse(response.error).message || response.error;
          } catch {
            // not JSON: shown as it is
          }
          setBusy(false);
          onError(message);
          return;
        }
        // Busy stays on through the route change, like the password sign-in.
        await onSignedIn();
      } catch (err) {
        if (mounted.current) setBusy(false);
        if (!live() || isPasskeyPromptCancelled(err)) return;
        onError(err instanceof Error ? err.message : "That passkey didn't work. Sign in another way.");
      }
    },
    [onError, onSignedIn],
  );

  return { busy, start };
}

export function useMyPasskeysQuery() {
  return useQuery<PasskeyItem[]>({
    queryKey: MY_PASSKEYS_KEY,
    queryFn: fetchMyPasskeys,
  });
}

export function useUserPasskeysQuery(userId: string, enabled = true) {
  return useQuery<PasskeyItem[]>({
    queryKey: userPasskeysKey(userId),
    queryFn: () => fetchUserPasskeys(userId),
    enabled: enabled && Boolean(userId),
  });
}

export function useSendPasskeyReauthCodeMutation() {
  return useMutation<{ sent_to: string }, Error, void>({
    mutationFn: () => sendPasskeyReauthCode(),
    onError: (err) => toast.error(err.message),
  });
}

/**
 * The whole add flow (AC-44): the re-check proof -> registration options -> the browser's own
 * prompt -> store. Resolves null when the user cancels the prompt, which shows nothing. A refusal
 * (wrong password or code, a duplicate passkey) is the caller's to show.
 */
export function useAddPasskeyMutation() {
  const qc = useQueryClient();
  return useMutation<PasskeyItem | null, Error, PasskeyProof>({
    mutationFn: async (proof) => {
      const { challenge_id, options } = await fetchPasskeyRegistrationOptions(proof);
      let credential;
      try {
        credential = await startRegistration({ optionsJSON: options });
      } catch (err) {
        if (isPasskeyPromptCancelled(err)) return null;
        throw err;
      }
      return registerPasskey(challenge_id, credential);
    },
    onSuccess: (added) => {
      if (!added) return;
      toast.success('Passkey added');
      qc.invalidateQueries({ queryKey: MY_PASSKEYS_KEY });
    },
    // No toast: the "Confirm it's you" dialog shows the refusal inline and stays open.
  });
}

export function useRenamePasskeyMutation() {
  const qc = useQueryClient();
  return useMutation<PasskeyItem, Error, { id: string; name: string }>({
    mutationFn: ({ id, name }) => renamePasskey(id, name),
    onSuccess: () => {
      toast.success('Passkey renamed');
      qc.invalidateQueries({ queryKey: MY_PASSKEYS_KEY });
    },
    onError: (err) => toast.error(err.message),
  });
}

export function useSetUserPasskeyEnabledMutation() {
  const qc = useQueryClient();
  return useMutation<
    { user_id: string; passkey_enabled: boolean },
    Error,
    { userId: string; enabled: boolean }
  >({
    mutationFn: ({ userId, enabled }) => setUserPasskeyEnabled(userId, enabled),
    onSuccess: (data, { userId }) => {
      toast.success(data.passkey_enabled ? 'Passkey sign-in turned on' : 'Passkey sign-in turned off');
      qc.invalidateQueries({ queryKey: ['user-user', userId] });
      // An admin switching their OWN row sees My account > Security update without a reload.
      qc.invalidateQueries({ queryKey: ['account-profile'] });
    },
    onError: (err) => toast.error(err.message),
  });
}
