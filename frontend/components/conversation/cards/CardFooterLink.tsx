import Link from "next/link";

export function CardFooterLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-accent transition-colors hover:text-accent-strong"
    >
      {label}
      <span aria-hidden="true" className="rtl:rotate-180">
        →
      </span>
    </Link>
  );
}
