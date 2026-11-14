import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { localeConfig } from "@/lib/locale";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Abdullah AI",
  description: "Don't just visit Abdullah's portfolio. Talk to Abdullah.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang={localeConfig.lang}
      dir={localeConfig.dir}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
