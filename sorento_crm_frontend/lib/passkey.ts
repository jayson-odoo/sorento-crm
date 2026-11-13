/** Browser-side passkey checks shared by the sign-in button and the Passkeys card (PASSKEY-LOGIN). */

/** Whether this browser, on this address, can use passkeys at all. */
export function browserCanUsePasskeys(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.PublicKeyCredential !== 'undefined' &&
    window.isSecureContext === true
  );
}

/** The user closed or dismissed the browser's own prompt, or a newer ceremony replaced it. */
export function isPasskeyPromptCancelled(err: unknown): boolean {
  const name = (err as { name?: string } | null)?.name;
  const code = (err as { code?: string } | null)?.code;
  return name === 'NotAllowedError' || name === 'AbortError' || code === 'ERROR_CEREMONY_ABORTED';
}
