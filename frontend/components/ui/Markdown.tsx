import ReactMarkdown, { type Components } from "react-markdown";

const components: Components = {
  a({ href, children }) {
    const external = href?.startsWith("http://") || href?.startsWith("https://");
    return external ? (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ) : (
      <a href={href}>{children}</a>
    );
  },
};

/**
 * Renders knowledge-base Markdown. Raw HTML is dropped (`skipHtml`) and react-markdown's
 * default URL transform strips unsafe protocols such as `javascript:`.
 */
export function Markdown({ children, className = "" }: { children: string; className?: string }) {
  return (
    <div className={`prose-lab ${className}`}>
      <ReactMarkdown skipHtml components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
