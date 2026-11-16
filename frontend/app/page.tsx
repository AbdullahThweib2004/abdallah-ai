import { existsSync } from "node:fs";
import path from "node:path";
import { Suspense } from "react";

import { ConversationHome } from "@/components/conversation/ConversationHome";
import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";
import { getContact, getProfile, getProjects } from "@/services/content";

const PORTRAIT = "/avatar/abdallah.jpg";

export default async function Home() {
  const [locale, profile, projects, contact] = await Promise.all([
    getLocale(),
    getProfile(),
    getProjects(),
    getContact(),
  ]);
  // Optional authorized portrait; the stage falls back to the orb when it is absent.
  const portraitSrc = existsSync(path.join(process.cwd(), "public", PORTRAIT)) ? PORTRAIT : null;

  return (
    <Suspense>
      <ConversationHome
        t={getDictionary(locale)}
        locale={locale}
        profile={profile}
        projects={projects}
        contact={contact}
        portraitSrc={portraitSrc}
      />
    </Suspense>
  );
}
