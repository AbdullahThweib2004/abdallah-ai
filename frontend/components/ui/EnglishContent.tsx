import type { ComponentPropsWithoutRef, ElementType } from "react";

type Props<T extends ElementType> = { as?: T } & ComponentPropsWithoutRef<T>;

/**
 * Knowledge-base content is English. Marking it lang="en" dir="ltr" keeps it correctly
 * shaped and ordered (and announced) inside the Arabic, right-to-left UI.
 */
export function EnglishContent<T extends ElementType = "div">({ as, ...props }: Props<T>) {
  const Component: ElementType = as ?? "div";
  return <Component lang="en" dir="ltr" {...props} />;
}
