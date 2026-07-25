'use client';

import Link from 'next/link';
import { ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface AccessDeniedProps {
  title?: string;
  description?: string;
}

const DEFAULT_TITLE = "You don't have access to this page";
const DEFAULT_DESCRIPTION =
  "Your role doesn't include permission for this area. If you think this is a mistake, ask an administrator to grant you access.";

/**
 * Shared "no access" state, rendered by page-level guards when the current user
 * lacks the required permission or superadmin role. Purely a UX surface — the
 * backend is the real enforcement (routes 403 for unauthorized principals).
 */
export default function AccessDenied({
  title = DEFAULT_TITLE,
  description = DEFAULT_DESCRIPTION,
}: AccessDeniedProps) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 py-10 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
        <ShieldAlert className="h-8 w-8 text-muted-foreground" />
      </div>
      <h1 className="mt-6 text-xl font-bold text-foreground">{title}</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
      <Button
        asChild
        className="mt-6 bg-destructive text-destructive-foreground hover:bg-destructive/90"
      >
        <Link href="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}
