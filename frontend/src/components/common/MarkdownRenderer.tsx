import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className = '' }) => {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  if (!content) return null;

  const handleCopy = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  // Split by code blocks first
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className={`space-y-2 text-xs leading-relaxed font-sans ${className}`}>
      {parts.map((part, partIdx) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          // Code block
          const lines = part.slice(3, -3).trim().split('\n');
          let lang = 'code';
          let codeBody = part.slice(3, -3).trim();

          if (lines.length > 0 && /^[a-zA-Z0-9_-]+$/.test(lines[0].trim())) {
            lang = lines[0].trim();
            codeBody = lines.slice(1).join('\n');
          }

          return (
            <div
              key={partIdx}
              className="my-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-100 overflow-hidden shadow-xs"
            >
              <div className="flex items-center justify-between px-3 py-1.5 bg-slate-950/80 border-b border-slate-800/80 text-[10px] font-mono text-slate-400">
                <span className="uppercase tracking-wider font-semibold">{lang}</span>
                <button
                  type="button"
                  onClick={() => handleCopy(codeBody, partIdx)}
                  className="flex items-center space-x-1 hover:text-white transition px-1.5 py-0.5 rounded hover:bg-slate-800"
                  title="Copy code"
                >
                  {copiedIndex === partIdx ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="p-3 overflow-x-auto text-[11px] font-mono leading-relaxed text-emerald-300/90 whitespace-pre">
                <code>{codeBody}</code>
              </pre>
            </div>
          );
        }

        // Render regular lines with inline formatting, lists, headings
        const paragraphs = part.split(/\n\n+/);
        return paragraphs.map((para, paraIdx) => {
          const lines = para.split('\n');
          const isList = lines.every((l) => /^\s*[-*•]\s+/.test(l) || /^\s*\d+\.\s+/.test(l));

          if (isList) {
            return (
              <ul key={`${partIdx}-${paraIdx}`} className="space-y-1 my-1 pl-4 list-disc list-outside text-slate-700 dark:text-slate-300">
                {lines.map((item, itemIdx) => {
                  const cleaned = item.replace(/^\s*[-*•]\s+/, '').replace(/^\s*\d+\.\s+/, '');
                  return (
                    <li key={itemIdx} className="pl-1">
                      {renderInline(cleaned)}
                    </li>
                  );
                })}
              </ul>
            );
          }

          // Check if paragraph starts with heading
          if (/^###\s+/.test(para)) {
            return (
              <h4 key={`${partIdx}-${paraIdx}`} className="font-bold text-slate-900 dark:text-slate-100 text-xs mt-2 mb-1">
                {renderInline(para.replace(/^###\s+/, ''))}
              </h4>
            );
          }
          if (/^##\s+/.test(para)) {
            return (
              <h3 key={`${partIdx}-${paraIdx}`} className="font-bold text-slate-900 dark:text-slate-100 text-sm mt-2.5 mb-1">
                {renderInline(para.replace(/^##\s+/, ''))}
              </h3>
            );
          }
          if (/^#\s+/.test(para)) {
            return (
              <h2 key={`${partIdx}-${paraIdx}`} className="font-extrabold text-slate-900 dark:text-white text-base mt-3 mb-1.5">
                {renderInline(para.replace(/^#\s+/, ''))}
              </h2>
            );
          }

          return (
            <p key={`${partIdx}-${paraIdx}`} className="text-slate-700 dark:text-slate-300">
              {lines.map((line, lIdx) => (
                <React.Fragment key={lIdx}>
                  {renderInline(line)}
                  {lIdx < lines.length - 1 && <br />}
                </React.Fragment>
              ))}
            </p>
          );
        });
      })}
    </div>
  );
};

// Helper to render bold, italic, and inline code spans
function renderInline(text: string): React.ReactNode[] {
  // Regex splitting by bold (**...**), inline code (`...`), and italics (*...*)
  const tokens = text.split(/(\*\*.*?\*\*|`.*?`|\*.*?\*)/g);
  return tokens.map((tok, idx) => {
    if (tok.startsWith('**') && tok.endsWith('**')) {
      return (
        <strong key={idx} className="font-semibold text-slate-900 dark:text-slate-100">
          {tok.slice(2, -2)}
        </strong>
      );
    }
    if (tok.startsWith('`') && tok.endsWith('`')) {
      return (
        <code
          key={idx}
          className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 font-mono text-[11px] border border-slate-200 dark:border-slate-700"
        >
          {tok.slice(1, -1)}
        </code>
      );
    }
    if (tok.startsWith('*') && tok.endsWith('*') && tok.length > 2) {
      return (
        <em key={idx} className="italic text-slate-800 dark:text-slate-200">
          {tok.slice(1, -1)}
        </em>
      );
    }
    return tok;
  });
}

