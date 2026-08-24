import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PriceFloorsListClient } from './components/PriceFloorsListClient';

/**
 * Price floors, on their own page.
 *
 * Split out of the old combined "Pricing policy" screen: floors are a different policy about
 * different products from a series, and sharing one page made both harder to read. No
 * explanatory subtitle, on the client's standing rule.
 */
export const metadata = { title: 'Price Floors' };

export default function Page() {
  return (
    <RequireAccess permission="projects.types.view">
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Price Floors</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Project Sales</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Price Floors</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions></ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <PriceFloorsListClient />
      </Container>
    </RequireAccess>
  );
}
