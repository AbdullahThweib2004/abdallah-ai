import { ContactSection } from "@/components/profile/ContactSection";
import type { Dictionary } from "@/lib/i18n/config";
import type { ContactResponse } from "@/services/types";

export function ContactCard({ contact, t }: { contact: ContactResponse; t: Dictionary }) {
  return <ContactSection links={contact.links} t={t} />;
}
