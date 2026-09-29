'use client';

import { Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { EmailThemeSocialLink } from '../types/emailTheme.types';

const MAX_SOCIAL_LINKS = 8;

export interface SocialLinksFieldProps {
  value: EmailThemeSocialLink[];
  onChange: (value: EmailThemeSocialLink[]) => void;
}

/** Social links as text rows (label + url), no icon images (Q3 / AC-EM007), max 8. */
export function SocialLinksField({ value, onChange }: SocialLinksFieldProps) {
  const patch = (index: number, patch: Partial<EmailThemeSocialLink>) => {
    onChange(value.map((link, i) => (i === index ? { ...link, ...patch } : link)));
  };
  const remove = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };
  const add = () => {
    if (value.length >= MAX_SOCIAL_LINKS) return;
    onChange([...value, { label: '', url: '' }]);
  };

  return (
    <div className="space-y-2">
      <Label>Social links</Label>
      {value.length === 0 ? (
        <p className="text-sm text-muted-foreground">No social links yet.</p>
      ) : (
        <div className="space-y-2">
          {value.map((link, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                aria-label="Social link label"
                value={link.label}
                onChange={(e) => patch(index, { label: e.target.value })}
                placeholder="LinkedIn"
                className="flex-1"
              />
              <Input
                aria-label="Social link URL"
                value={link.url}
                onChange={(e) => patch(index, { url: e.target.value })}
                placeholder="https://linkedin.com/company/..."
                className="flex-1"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="size-8 shrink-0 p-0 text-destructive"
                aria-label="Remove social link"
                onClick={() => remove(index)}
              >
                <X className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={add}
        disabled={value.length >= MAX_SOCIAL_LINKS}
      >
        <Plus className="mr-1 size-4" /> Add social link
      </Button>
    </div>
  );
}

export default SocialLinksField;
