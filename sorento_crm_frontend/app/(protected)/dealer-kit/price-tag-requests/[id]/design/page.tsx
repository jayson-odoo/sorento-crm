import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import RequestTagDesignerShell from './components/RequestTagDesignerShell';

export const metadata: Metadata = {
  title: 'Design Price Tags',
  description: "Design a price tag request's tags",
};

export default async function TagSheetDesignPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="flex h-[calc(100dvh-var(--header-height)-20px)] flex-col">
      {/* PageHeader keeps the trail and title one component (S5-01, S5-02)
          even though this shell sits outside the normal scrolling Toolbar
          rhythm - shrink-0 so the canvas below still gets whatever height is
          left, exactly as the old compact bar did.
          The 100dvh subtracts the fixed top bar's own height (the demo1
          layout's `--header-height`, 70px desktop / 60px below lg) plus the
          `<main>` wrapper's `pt-5` (20px) - both chrome above this div that a
          flat 56px never accounted for and left the canvas short. */}
      <div className="shrink-0 border-b bg-background">
        <Container>
          <PageHeader
            title="Design Price Tags"
            actions={
              <BackToList
                listPath={`/dealer-kit/price-tag-requests/${id}`}
                label="Back to request"
                appendListState={false}
              />
            }
          />
        </Container>
      </div>
      <div className="flex-1 overflow-hidden">
        <RequestTagDesignerShell requestId={id} />
      </div>
    </div>
  );
}
