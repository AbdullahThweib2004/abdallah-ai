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
  title: "Abdallah AI",
  description: "Don't just visit Abdallah's portfolio. Talk to Abdallah.",
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
