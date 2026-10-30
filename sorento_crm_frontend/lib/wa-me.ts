/** Build a WhatsApp click-to-chat URL with prefilled text. */
export function waMeUrl(phoneNumber: string, text: string): string {
  const digits = phoneNumber.replace(/\D/g, '');
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}
