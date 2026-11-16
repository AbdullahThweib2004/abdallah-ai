export const en = {
  meta: {
    title: "Abdallah AI",
    description: "Don't just visit Abdallah's portfolio. Talk to Abdallah.",
  },
  brand: "Abdallah AI",
  tagline: "Don't just visit Abdallah's portfolio. Talk to Abdallah.",
  skipToContent: "Skip to content",
  nav: {
    label: "Main",
    menu: "Menu",
    projects: "Projects",
    about: "About",
    skills: "Skills",
    contact: "Contact",
  },
  language: {
    label: "Language",
    en: "EN",
    ar: "ع",
  },
  hero: {
    eyebrow: "Interactive AI portfolio",
    greetingLabel: "Greeting from Abdallah AI",
  },
  conversation: {
    title: "Conversation",
    comingSoon: "Conversation coming soon",
    description:
      "Soon you will be able to talk with Abdallah AI by text or voice and ask about his projects, experience and skills.",
    button: "Talk to Abdallah AI",
    transparency: "Abdallah AI is an AI representation of Abdallah, not Abdallah himself.",
  },
  sections: {
    featured: "Featured projects",
    allProjects: "All projects",
    about: "About",
    experience: "Experience",
    education: "Education",
    skills: "Skills",
    interests: "Interests",
    direction: "Career direction",
    contact: "Contact",
  },
  profile: {
    location: "Location",
    languages: "Languages",
    waysOfWorking: "Ways of working",
  },
  projects: {
    viewDetails: "View details",
    detailsFor: "Details for",
    technologies: "Technologies",
    status: "Status",
    repository: "View repository",
    demo: "Open demo",
    lastReviewed: "Last reviewed",
    backToProjects: "Back to all projects",
    moreTech: "more",
    statusLabels: {
      completed: "Completed",
      in_progress: "In progress",
      research: "Research",
    },
  },
  contact: {
    intro: "Public links for getting in touch.",
    opensInNewTab: "opens in a new tab",
  },
  unavailable: {
    title: "Content temporarily unavailable",
    body: "The portfolio content could not be loaded right now. Please try again in a moment.",
  },
  notFound: {
    title: "Page not found",
    body: "This page does not exist or is no longer public.",
    home: "Go to the home page",
  },
  footer: {
    note: "An AI-powered interactive portfolio. Content comes from a reviewed knowledge base.",
    backend: {
      checking: "Checking backend…",
      online: "Backend online",
      offline: "Backend offline",
    },
  },
};

type Widen<T> = { [K in keyof T]: T[K] extends string ? string : Widen<T[K]> };

export type Dictionary = Widen<typeof en>;
