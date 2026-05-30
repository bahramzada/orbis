import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

export function MarkdownContent({
  content,
  initialLineLimit = 0
}: {
  content: string;
  initialLineLimit?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const lines = useMemo(() => content.split("\n"), [content]);
  const visibleLines =
    initialLineLimit > 0 && !isExpanded ? lines.slice(0, initialLineLimit) : lines;
  const hiddenLineCount = Math.max(0, lines.length - visibleLines.length);

  useEffect(() => {
    setIsExpanded(false);
  }, [content]);

  return (
    <div className="markdown-content">
      {visibleLines.map((line, index) => renderMarkdownLine(line, index))}
      {hiddenLineCount > 0 ? (
        <button
          className="show-more-button"
          onClick={() => setIsExpanded(true)}
          type="button"
        >
          Show {hiddenLineCount} more lines
        </button>
      ) : null}
    </div>
  );
}

function renderMarkdownLine(line: string, index: number) {
  const trimmed = line.trim();
  if (!trimmed) {
    return null;
  }
  if (/^-{3,}$/.test(trimmed)) {
    return <hr key={`${index}-${trimmed}`} />;
  }
  if (trimmed.startsWith("### ")) {
    return <h5 key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed.slice(4))}</h5>;
  }
  if (trimmed.startsWith("## ")) {
    return <h4 key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed.slice(3))}</h4>;
  }
  if (trimmed.startsWith("# ")) {
    return <h4 key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed.slice(2))}</h4>;
  }
  if (/^[-*]\s+/.test(trimmed)) {
    return (
      <p className="markdown-list-line" key={`${index}-${trimmed}`}>
        {renderInlineMarkdown(trimmed.replace(/^[-*]\s+/, ""))}
      </p>
    );
  }
  if (/^\d+\.\s+/.test(trimmed)) {
    return (
      <p className="markdown-list-line numbered" key={`${index}-${trimmed}`}>
        {renderInlineMarkdown(trimmed)}
      </p>
    );
  }
  if (trimmed.startsWith("|")) {
    return (
      <pre className="markdown-table-line" key={`${index}-${trimmed}`}>
        {trimmed}
      </pre>
    );
  }
  return <p key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed)}</p>;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${index}-${part}`}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}
