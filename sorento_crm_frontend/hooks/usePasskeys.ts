/**
 * Passkey queries and mutations (PASSKEY-LOGIN). UI -> these hooks -> services/passkeyService.
 * Removal is not here: it is the deferred record action `user_passkey.delete`
 * (`useDeferredAction`), parked per row.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { startRegistration } from '@simplewebauthn/browser';
import { toast } from '@/lib/toast';
import { isPasskeyPromptCancelled } from '@/lib/passkey';

import {
  fetchMyPasskeys,
  fetchPasskeyRegistrationOptions,
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
 * prompt -> store. Resolves null when the user cancels the prompt, which shows nothing.
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
    onError: (err) => toast.error(err.message),
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
    },
    onError: (err) => toast.error(err.message),
  });
}
