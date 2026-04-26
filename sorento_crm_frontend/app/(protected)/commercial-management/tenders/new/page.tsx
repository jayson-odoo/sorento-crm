import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import NewTenderForm from '../components/NewTenderForm';

export const metadata: Metadata = {
  title: 'New tender',
};

export default function NewTenderPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>New tender</ToolbarTitle>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container>
        <NewTenderForm />
      </Container>
    </>
  );
}
