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
      {renderMarkdownBlocks(visibleLines)}
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

function renderMarkdownBlocks(lines: string[]) {
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const nextLine = lines[index + 1] ?? "";

    if (isTableRow(line) && isTableSeparator(nextLine)) {
      const tableLines = [line];
      index += 2;

      while (index < lines.length && isTableRow(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }

      blocks.push(renderMarkdownTable(tableLines, blocks.length));
      continue;
    }

    blocks.push(renderMarkdownLine(line, index));
    index += 1;
  }

  return blocks;
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
  return <p key={`${index}-${trimmed}`}>{renderInlineMarkdown(trimmed)}</p>;
}

function renderMarkdownTable(lines: string[], index: number) {
  const [headerLine, ...bodyLines] = lines;
  const headers = parseTableCells(headerLine);
  const rows = bodyLines.filter((line) => !isTableSeparator(line)).map(parseTableCells);

  return (
    <div className="markdown-table-wrap" key={`table-${index}`}>
      <table className="markdown-table">
        <thead>
          <tr>
            {headers.map((header, cellIndex) => (
              <th key={`head-${cellIndex}`}>{renderInlineMarkdown(header)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`}>
              {headers.map((_, cellIndex) => (
                <td key={`cell-${rowIndex}-${cellIndex}`}>
                  {renderInlineMarkdown(row[cellIndex] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isTableRow(line: string) {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && trimmed.includes("|", 1);
}

function isTableSeparator(line: string) {
  const cells = parseTableCells(line);
  return (
    cells.length > 0 &&
    cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")))
  );
}

function parseTableCells(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${index}-${part}`}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}
