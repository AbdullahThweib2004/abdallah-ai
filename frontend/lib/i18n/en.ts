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
    contact: "Contact",
  },
  language: {
    label: "Language",
    en: "EN",
    ar: "ع",
  },
  avatar: {
    label: "Abdallah AI avatar",
    states: {
      idle: "Ready",
      listening: "Listening",
      thinking: "Thinking",
      speaking: "Speaking",
    },
  },
  conversation: {
    regionLabel: "Conversation with Abdallah AI",
    suggestionsLabel: "Suggested questions",
    suggestions: [
      "What's his strongest project?",
      "Tell me about his training at Bank of Palestine",
      "What does he know about RAG and MCP?",
      "How can I contact him?",
    ],
    inputLabel: "Ask Abdallah AI a question",
    placeholder: "Ask about his projects, skills or experience…",
    send: "Send",
    mic: "Voice input",
    voiceSoon: "Voice is coming soon",
    transparency: "Abdallah AI is an AI representation of Abdallah, not Abdallah himself.",
    you: "You",
    assistant: "Abdallah AI",
    history: "History",
    historyTitle: "Conversation history",
    replies: {
      related: "Live conversation is launching soon. Meanwhile, here's what's related:",
      noMatch: "Live conversation is launching soon. Meanwhile, try one of these questions:",
      askProject: "Live conversation is launching soon. Meanwhile, here's the project you asked about:",
    },
  },
  cards: {
    close: "Close",
    titles: {
      show_project: "Project",
      show_projects: "All projects",
      show_skills: "Skills",
      show_experience: "Experience",
      show_education: "Education",
      show_contact: "Contact",
    },
    openProject: "Open project",
    allProjectsLink: "Browse all projects",
    aboutLink: "Full profile",
  },
  pages: {
    aboutTitle: "About Abdallah",
    projectsTitle: "Projects",
    projectsIntro: "Everything Abdallah has built, featured work first.",
    talkCta: "Talk to Abdallah AI",
    askAboutProject: "Ask Abdallah AI about this project",
  },
  sections: {
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
