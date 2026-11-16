"use server";

import { cookies } from "next/headers";

import { LOCALE_COOKIE, isLocale } from "./config";

const ONE_YEAR = 60 * 60 * 24 * 365;

/** Persist the UI language. Setting a cookie in a Server Function re-renders the page. */
export async function setLocale(locale: string): Promise<void> {
  if (!isLocale(locale)) return;
  (await cookies()).set(LOCALE_COOKIE, locale, {
    path: "/",
    maxAge: ONE_YEAR,
    sameSite: "lax",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
  });
}
