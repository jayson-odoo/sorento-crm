'use client';

import { createContext, ReactNode, useContext } from 'react';
import type { RespondContact } from '../../types/contact.types';

interface ContactContextProps {
  /** Undefined while the record loads, or when it does not exist. */
  contact: RespondContact | undefined;
  isLoading: boolean;
  /** Route id, available before the record resolves so sections can fetch on their own. */
  contactId: string;
}

interface ContactProviderProps extends ContactContextProps {
  children: ReactNode;
}

const ContactContext = createContext<ContactContextProps | undefined>(undefined);

export const useContact = () => {
  const context = useContext(ContactContext);
  if (!context) {
    throw new Error('useContact must be used within a ContactProvider');
  }
  return context;
};

export const ContactProvider = ({
  contact,
  isLoading,
  contactId,
  children,
}: ContactProviderProps) => {
  return (
    <ContactContext.Provider value={{ contact, isLoading, contactId }}>
      {children}
    </ContactContext.Provider>
  );
};
