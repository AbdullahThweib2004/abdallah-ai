import Link from "next/link";

import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";

export default async function NotFound() {
  const t = getDictionary(await getLocale());

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-start px-4 py-32 sm:px-6">
      <p className="font-mono text-sm text-accent">404</p>
      <h1 className="mt-4 text-3xl font-semibold text-mist-50">{t.notFound.title}</h1>
      <p className="mt-3 text-mist-200">{t.notFound.body}</p>
      <Link
        href="/"
        className="mt-8 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink hover:bg-accent-strong"
      >
        {t.notFound.home}
      </Link>
    </div>
  );
}
