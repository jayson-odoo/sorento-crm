'use client';

import { useState, type ReactNode } from 'react';
import { Link as LinkIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { useHasPermission } from '@/hooks/usePermissions';
import PortalLinkDialog from './PortalLinkDialog';

export interface PortalLinkButtonProps {
  contactId: string;
  contactLabel?: string;
  canSendViaRespondIo?: boolean;
  variant?: 'button' | 'menu-item' | 'icon';
  disabled?: boolean;
  children?: ReactNode;
}

const PERMISSION_SLUG = 'user_management.contacts.portal_link';

export default function PortalLinkButton({
  contactId,
  contactLabel,
  canSendViaRespondIo,
  variant = 'button',
  disabled,
  children,
}: PortalLinkButtonProps) {
  const allowed = useHasPermission(PERMISSION_SLUG);
  const [open, setOpen] = useState(false);

  if (!allowed) return null;

  const trigger = (() => {
    if (variant === 'menu-item') {
      return (
        <DropdownMenuItem
          onSelect={(e) => {
            e.preventDefault();
            setOpen(true);
          }}
          disabled={disabled}
        >
          <LinkIcon className="size-4 mr-2" />
          {children ?? 'Portal link'}
        </DropdownMenuItem>
      );
    }
    if (variant === 'icon') {
      return (
        <Button
          variant="ghost"
          size="sm"
          title="Portal link"
        aria-label="Portal link"
          disabled={disabled}
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
        >
          <LinkIcon className="size-4" />
        </Button>
      );
    }
    return (
      <Button
        variant="outline"
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        <LinkIcon className="size-4 mr-2" />
        {children ?? 'Portal link'}
      </Button>
    );
  })();

  return (
    <>
      {trigger}
      <PortalLinkDialog
        open={open}
        onOpenChange={setOpen}
        contactId={contactId}
        contactLabel={contactLabel}
        canSendViaRespondIo={canSendViaRespondIo}
      />
    </>
  );
}
