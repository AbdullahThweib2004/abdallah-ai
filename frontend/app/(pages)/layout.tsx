import { SiteFooter } from "@/components/ui/SiteFooter";
import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";

/** Content pages (about, projects) scroll and get the footer; the home page is one screen. */
export default async function PagesLayout({ children }: LayoutProps<"/">) {
  const t = getDictionary(await getLocale());
  return (
    <>
      {children}
      <SiteFooter t={t} />
    </>
  );
}
