type Props = { label: string; suggestions: string[]; onPick: (text: string) => void };

export function SuggestionChips({ label, suggestions, onPick }: Props) {
  return (
    <ul
      aria-label={label}
      className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:justify-center sm:overflow-visible sm:px-0"
    >
      {suggestions.map((suggestion) => (
        <li key={suggestion} className="shrink-0">
          <button
            type="button"
            onClick={() => onPick(suggestion)}
            className="whitespace-nowrap rounded-full border border-ink-700 bg-ink-900/80 px-3.5 py-1.5 text-sm text-mist-200 transition-colors hover:border-accent/60 hover:text-mist-50"
          >
            {suggestion}
          </button>
        </li>
      ))}
    </ul>
  );
}
