import { HomeSkeleton } from "@/components/ui/Skeletons";
import { cookies } from "next/headers";
import { Suspense } from "react";

import { ConversationHome } from "@/components/conversation/ConversationHome";
import { getDictionary } from "@/lib/i18n/config";
import { VOICE_REPLIES_COOKIE, parseVoiceReplies } from "@/lib/voice/preferences";
import { getLocale } from "@/lib/i18n/server";
import { getContact, getProfile, getProjects } from "@/services/content";

async function HomeContent() {
  const [locale, profile, projects, contact, cookieStore] = await Promise.all([
    getLocale(),
    getProfile(),
    getProjects(),
    getContact(),
    cookies(),
  ]);

  return (
    <Suspense>
      <ConversationHome
        t={getDictionary(locale)}
        locale={locale}
        profile={profile}
        projects={projects}
        contact={contact}
        voiceReplies={parseVoiceReplies(cookieStore.get(VOICE_REPLIES_COOKIE)?.value)}
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
