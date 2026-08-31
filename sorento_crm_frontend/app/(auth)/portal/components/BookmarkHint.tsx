'use client';

/**
 * One-time dismissible hint shown on the first verified visit to the stable
 * slug URL - nudges the user to keep their personal portal link.
 *
 * Browsers do not allow JS to write to the bookmark bar (security), so the
 * closest one-tap equivalents are offered instead:
 * - native share sheet on mobile (navigator.share) - covers "Add to Home
 *   Screen" / "send to myself" flows, which is how WhatsApp-first users
 *   actually keep links;
 * - copy-to-clipboard everywhere else;
 * - plus the ⌘D / Ctrl+D keyboard tip for desktop browsers.
 */

import { useEffect, useState } from 'react';
import { Bookmark, Check, Copy, Share2, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';

const DISMISS_KEY = 'sorento.portalBookmarkHintDismissed';

export function BookmarkHint() {
  const [visible, setVisible] = useState(false);
  const [canShare, setCanShare] = useState(false);
  const [isMac, setIsMac] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setVisible(window.localStorage.getItem(DISMISS_KEY) !== '1');
    setCanShare(typeof navigator !== 'undefined' && typeof navigator.share === 'function');
    setIsMac(/Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent));
  }, []);

  if (!visible) return null;

  const stableUrl = () =>
    typeof window !== 'undefined'
      ? window.location.origin + window.location.pathname
      : '';

  const dismiss = () => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(DISMISS_KEY, '1');
    }
    setVisible(false);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(stableUrl());
      // The button already says Copied; a toast on top of it is the app telling
      // the reader what they just did (S7-05).
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Could not copy. Long-press the address bar to copy the link.');
    }
  };

  const handleShare = async () => {
    try {
      await navigator.share({ title: 'My Sorento portal', url: stableUrl() });
    } catch {
      // user cancelled the sheet - not an error
    }
  };

  return (
    <div
      className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2.5 space-y-2"
      data-testid="bookmark-hint"
    >
      <div className="flex items-start gap-2">
        <Bookmark className="h-4 w-4 mt-0.5 shrink-0 text-primary" aria-hidden />
        <p className="text-xs text-foreground/80 flex-1">
          This page is your personal portal link - keep it to come back any time
          without asking for a new link.
          <span className="hidden sm:inline">
            {' '}
            Press <kbd className="rounded border bg-muted px-1 font-mono text-[10px]">
              {isMac ? '⌘D' : 'Ctrl+D'}
            </kbd>{' '}
            to bookmark.
          </span>
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={dismiss}
          className="h-6 w-6 p-0 shrink-0 -mr-1"
          aria-label="Dismiss bookmark hint"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="flex gap-2 pl-6">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleCopy}
          className="h-8 text-xs"
          data-testid="bookmark-copy"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 mr-1.5 text-success" />
          ) : (
            <Copy className="h-3.5 w-3.5 mr-1.5" />
          )}
          {copied ? 'Copied' : 'Copy link'}
        </Button>
        {canShare && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleShare}
            className="h-8 text-xs"
            data-testid="bookmark-share"
          >
            <Share2 className="h-3.5 w-3.5 mr-1.5" />
            Share / save
          </Button>
        )}
      </div>
    </div>
  );
}
