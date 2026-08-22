import { Metadata } from 'next';
import { QuotationSignClient } from './components/QuotationSignClient';

export const metadata: Metadata = {
  title: 'Quotation',
  description: 'Read the quotation and sign to accept it.',
  // A tokenised link is a private artifact even though the route is public. Indexing one would
  // publish a customer's prices to anybody searching for the reference.
  robots: { index: false, follow: false },
};

/**
 * The customer's counter-sign page: `/quotation-sign/{token}`.
 *
 * Lives under `(auth)` with the other contact-facing pages (`/view`, `/portal`), NOT under
 * `(protected)`: the signer is a stranger holding a link, with no CRM account, and the protected
 * layout would bounce them to the sign-in screen. `(auth)` gives them the branded card and no app
 * chrome - no sidebar, no nav, nothing to get lost in on a phone.
 *
 * The token is the only credential and it never leaves this page: the backend resolves it to ONE
 * issue, so nothing here takes or exposes an id.
 */
export default async function QuotationSignPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <QuotationSignClient token={token} />;
}
