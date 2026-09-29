import type { Metadata } from 'next';
import EmailThemeForm from './components/EmailThemeForm';

export const metadata: Metadata = {
  title: 'Email Theme',
  description: 'Brand every outgoing mail: logo, colours, button style, font and footer.',
};

export default function EmailThemePage() {
  return <EmailThemeForm />;
}
