import { BackendStatusBadge } from "@/components/ui/BackendStatusBadge";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-24 text-center">
      <h1 className="text-5xl font-semibold tracking-tight sm:text-6xl">Abdullah AI</h1>
      <p className="max-w-xl text-lg text-zinc-600 dark:text-zinc-400">
        Don&apos;t just visit Abdullah&apos;s portfolio. Talk to Abdullah.
      </p>
      <BackendStatusBadge />
    </main>
  );
}
