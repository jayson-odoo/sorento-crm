import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import PromotionAttachmentsList from './components/PromotionAttachmentsList';

export const metadata: Metadata = {
  title: 'Promotion Attachments | Sorento CRM',
};

export default function PromotionAttachmentsPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Promotion Attachments</ToolbarTitle>
          </ToolbarHeading>
        </Toolbar>
      </Container>

      <Container>
        <PromotionAttachmentsList />
      </Container>
    </>
  );
}
