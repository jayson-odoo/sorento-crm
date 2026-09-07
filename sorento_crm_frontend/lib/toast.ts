import { toast as sonnerToast } from 'sonner';
import type { ExternalToast } from 'sonner';

/**
 * The one toast standard (M6-04, revised 2026-09-07).
 *
 * Every toast auto-dismisses - a success clears itself fast (4s), an error
 * sits a little longer (5s) so it is readable, and the close button covers
 * "I want it gone before the timer." M6-04 originally made errors sticky
 * (`duration: Infinity`) on the theory that an auto-dismissed error while the
 * reader looked away read as "nothing happened"; in practice a failing
 * background refetch (window focus, `refetchInterval` polling, an
 * invalidation) re-raised that toast every cycle, so a sticky error toast
 * never seemed to leave the screen at all. `providers/query-provider.tsx`
 * carries the fix for the repeat case (only the first failure of a given
 * query toasts); every error toast in the app just needs to not be stuck.
 *
 * Every call site imports `toast` from HERE, never from `'sonner'` directly
 * (`lib/toast.inventory.test.ts` holds the floor); `components/ui/sonner.tsx`
 * is the one file allowed to import sonner itself, because it is what mounts
 * the `<Toaster>`.
 *
 * A caller that already passes its own `duration` or `closeButton` wins - this
 * only sets the DEFAULT, the same way `sonnerToast.success(msg, opts)` always
 * let `opts` override its own defaults.
 *
 * `promise`, `custom` and `warning` are deliberate raw passthroughs, not
 * bugs: nothing in the app calls `toast.promise` today (its error branch
 * would need to unwrap a string/JSX/function result, which is machinery with
 * no caller to justify it - see PRINCIPLES.md "simplest thing that works"),
 * and every live `toast.custom` call site already sets its own `duration`/
 * `close` per call (query-provider's error path included), which is the same
 * "caller wins" contract this file enforces for `success`/`error`.
 */
const SUCCESS_DURATION_MS = 4000;
const ERROR_DURATION_MS = 5000;

type Message = Parameters<typeof sonnerToast>[0];

function success(message: Message, data?: ExternalToast) {
  return sonnerToast.success(message, { duration: SUCCESS_DURATION_MS, ...data });
}

function error(message: Message, data?: ExternalToast) {
  return sonnerToast.error(message, { duration: ERROR_DURATION_MS, closeButton: true, ...data });
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
