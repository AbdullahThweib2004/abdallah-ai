import type { ReactNode } from "react";

export function PageHeader({ title, intro, action }: { title: string; intro?: string; action?: ReactNode }) {
  return (
    <header className="lab-backdrop">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 pb-12 pt-16 sm:flex-row sm:items-end sm:justify-between sm:px-6 lg:px-8">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight text-mist-50 sm:text-5xl">{title}</h1>
          {intro && <p className="mt-4 max-w-2xl text-lg text-mist-200">{intro}</p>}
        </div>
        {action}
      </div>
    </header>
  );
}
