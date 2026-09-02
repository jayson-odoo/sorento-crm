import { toast as sonnerToast } from 'sonner';
import type { ExternalToast } from 'sonner';

/**
 * The one toast standard (M6-04).
 *
 * A success clears itself - the reader already saw it land, and a stack of
 * toasts that never age out is its own kind of noise. An error does the
 * opposite: it waits for the reader to dismiss it, because a network failure
 * that auto-dismissed while the reader was looking away used to read as
 * "nothing happened" rather than "it failed" - the close button is what makes
 * "wait for me" legible instead of stuck.
 *
 * Every call site imports `toast` from HERE, never from `'sonner'` directly
 * (`lib/toast.inventory.test.ts` holds the floor); `components/ui/sonner.tsx`
 * is the one file allowed to import sonner itself, because it is what mounts
 * the `<Toaster>`.
 *
 * A caller that already passes its own `duration` or `closeButton` wins - this
 * only sets the DEFAULT, the same way `sonnerToast.success(msg, opts)` always
 * let `opts` override its own defaults.
 */
const SUCCESS_DURATION_MS = 4000;

type Message = Parameters<typeof sonnerToast>[0];

function success(message: Message, data?: ExternalToast) {
  return sonnerToast.success(message, { duration: SUCCESS_DURATION_MS, ...data });
}

function error(message: Message, data?: ExternalToast) {
  return sonnerToast.error(message, { duration: Infinity, closeButton: true, ...data });
}

export const toast = Object.assign(
  (message: Message, data?: ExternalToast) => sonnerToast(message, data),
  {
    success,
    error,
    info: sonnerToast.info,
    warning: sonnerToast.warning,
    message: sonnerToast.message,
    promise: sonnerToast.promise,
    dismiss: sonnerToast.dismiss,
    loading: sonnerToast.loading,
    custom: sonnerToast.custom,
    getHistory: sonnerToast.getHistory,
    getToasts: sonnerToast.getToasts,
  },
);
