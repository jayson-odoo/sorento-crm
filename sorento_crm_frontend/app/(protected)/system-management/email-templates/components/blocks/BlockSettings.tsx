'use client';

import type { AnyBlockPatch, EmailBlock } from '../../types/emailTemplate.types';
import { HeadingSettings } from './HeadingSettings';
import { IntroSettings } from './IntroSettings';
import { FactsSettings } from './FactsSettings';
import { LabelUrlSettings } from './LabelUrlSettings';
import { CustomTextSettings } from './CustomTextSettings';
import { FooterSettings } from './FooterSettings';

/** Dispatches each block to its own settings body (AC-EM043). Brand header
 * has nothing to configure - it always shows the theme's logo/company name. */
export function BlockSettings({
  block,
  onChange,
}: {
  block: EmailBlock;
  onChange: (patch: AnyBlockPatch) => void;
}) {
  switch (block.type) {
    case 'brand_header':
      return (
        <p className="text-sm text-muted-foreground">
          Shows the theme&rsquo;s logo (or company name) on the brand band.
        </p>
      );
    case 'heading':
      return <HeadingSettings block={block} onChange={onChange} />;
    case 'intro':
      return <IntroSettings block={block} onChange={onChange} />;
    case 'facts':
      return <FactsSettings block={block} onChange={onChange} />;
    case 'button':
      return <LabelUrlSettings block={block} onChange={onChange} urlPlaceholder="{{ reset_link }}" />;
    case 'link':
      return (
        <LabelUrlSettings
          block={block}
          onChange={onChange}
          urlPlaceholder="Or paste this link into your browser:"
        />
      );
    case 'custom_text':
      return <CustomTextSettings block={block} onChange={onChange} />;
    case 'footer':
      return <FooterSettings block={block} onChange={onChange} />;
    default:
      return null;
  }
}

export default BlockSettings;
