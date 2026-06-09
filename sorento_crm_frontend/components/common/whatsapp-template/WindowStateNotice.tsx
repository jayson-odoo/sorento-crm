'use client';

import { Clock } from 'lucide-react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { WindowState } from '@/services/whatsappTemplateService';

interface WindowStateNoticeProps {
  windowState: WindowState;
}

/**
 * Amber banner shown above the chat compose box when the contact's 24-hour
 * WhatsApp messaging window is closed. Plain messages are silently dropped by
 * WhatsApp in that state — only approved templates are delivered.
 */
export default function WindowStateNotice({ windowState }: WindowStateNoticeProps) {
  if (windowState.open) return null;
  return (
    <div
      className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
      data-testid="window-closed-notice"
    >
      <Clock className="size-3.5 mt-0.5 shrink-0" />
      <div>
        <span className="font-medium">24-hour window closed.</span>{' '}
        Plain messages will not be delivered — send a template to re-open the
        conversation.
        {windowState.last_incoming_at && (
          <span className="text-amber-700 dark:text-amber-300">
            {' '}
            Last reply from contact: {formatDateTimeInMalaysia(windowState.last_incoming_at)}.
          </span>
        )}
      </div>
    </div>
  );
}
