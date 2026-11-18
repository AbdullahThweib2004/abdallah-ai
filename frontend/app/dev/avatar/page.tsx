import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AvatarPreview } from "./AvatarPreview";

export const metadata: Metadata = { title: "Avatar preview (dev)", robots: { index: false } };

/** Development-only tuning page for the robot avatar; 404 in production builds. */
export default function DevAvatarPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <AvatarPreview />;
}
