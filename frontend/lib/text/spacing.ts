// An Arabic letter (incl. tatweel) directly followed by a Latin letter: "وReact", "بـMCP".
const ARABIC_THEN_LATIN = /([ء-يـٱ-ۓ])([A-Za-z])/g;

/**
 * Insert the space the model sometimes forgets between an Arabic letter and a following
 * Latin letter ("وReact" → "و React"), so captions read correctly and TTS does not merge the
 * two words. Display and speech only: the stored answer (history, evals) stays as generated.
 */
export function spaceArabicLatin(text: string): string {
  return text.replace(ARABIC_THEN_LATIN, "$1 $2");
}
