import { ConversationPlaceholder } from "@/components/conversation/ConversationPlaceholder";
import { EnglishContent } from "@/components/ui/EnglishContent";
import type { Dictionary, Locale } from "@/lib/i18n/config";
import type { Profile } from "@/services/types";

type Props = { profile: Profile | null; t: Dictionary; locale: Locale };

export function Hero({ profile, t, locale }: Props) {
  const arabic = locale === "ar";
  const showArabicName = arabic && Boolean(profile?.name_ar);
  const greeting = arabic ? profile?.intro.ar : profile?.intro.en;

  return (
    <div className="lab-backdrop">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-16 sm:px-6 sm:pt-24 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16 lg:px-8">
        <div>
          <p className="reveal font-mono text-xs uppercase tracking-[0.25em] text-accent">{t.hero.eyebrow}</p>

          <h1 className="reveal mt-6 text-5xl font-semibold leading-[1.05] tracking-tight text-mist-50 sm:text-6xl lg:text-7xl" style={{ ["--reveal-delay" as string]: "60ms" }}>
            {profile ? (
              showArabicName ? (
                <>
                  <span lang="ar">{profile.name_ar}</span>
                  <span lang="en" dir="ltr" className="mt-3 block text-2xl font-normal tracking-normal text-mist-400 sm:text-3xl">
                    {profile.name}
                  </span>
                </>
              ) : (
                <span lang="en">{profile.name}</span>
              )
            ) : (
              <span lang="en">{t.brand}</span>
            )}
          </h1>

          {profile && (
            <EnglishContent as="p" className="reveal mt-5 font-mono text-sm text-mist-200 sm:text-base" style={{ ["--reveal-delay" as string]: "120ms" }}>
              {profile.headline}
            </EnglishContent>
          )}

          <p className="reveal mt-8 max-w-xl text-xl leading-relaxed text-mist-50 sm:text-2xl" style={{ ["--reveal-delay" as string]: "180ms" }}>
            {t.tagline}
          </p>

          {greeting && (
            <figure className="reveal mt-10 max-w-xl border-s-2 border-accent/70 ps-5" style={{ ["--reveal-delay" as string]: "240ms" }}>
              <figcaption className="mb-2 font-mono text-xs uppercase tracking-[0.2em] text-mist-400">
                {t.hero.greetingLabel}
              </figcaption>
              <blockquote
                lang={arabic ? "ar" : "en"}
                dir={arabic ? "rtl" : "ltr"}
                className="text-base leading-relaxed text-mist-200"
              >
                <p>“{greeting}”</p>
              </blockquote>
            </figure>
          )}
        </div>

        <div className="reveal" style={{ ["--reveal-delay" as string]: "200ms" }}>
          <ConversationPlaceholder t={t} />
        </div>
      </div>
    </div>
  );
}
