import { HomeSkeleton } from "@/components/ui/Skeletons";
import { existsSync } from "node:fs";
import path from "node:path";
import { Suspense } from "react";

import { ConversationHome } from "@/components/conversation/ConversationHome";
import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";
import { getContact, getProfile, getProjects } from "@/services/content";

const PORTRAIT = "/avatar/abdallah.jpg";

async function HomeContent() {
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


// Request-time data (locale cookie, backend content) streams inside Suspense; the fallback is
// the static shell, so navigations stay instant under cacheComponents.
export default function Home() {
  return (
    <Suspense fallback={<HomeSkeleton />}>
      <HomeContent />
    </Suspense>
  );
}
