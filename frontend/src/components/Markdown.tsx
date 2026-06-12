import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Render markdown thành tài liệu đọc, style theo semantic token (sáng/tối).
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed text-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h1 className="mb-3 mt-1 text-xl font-bold text-text" {...p} />,
          h2: (p) => (
            <h2 className="mb-2 mt-5 border-b border-border pb-1 text-lg font-semibold text-text" {...p} />
          ),
          h3: (p) => <h3 className="mb-1 mt-4 text-base font-semibold text-text" {...p} />,
          p: (p) => <p className="my-2 text-muted" {...p} />,
          ul: (p) => <ul className="my-2 list-disc space-y-1 pl-5 text-muted" {...p} />,
          ol: (p) => <ol className="my-2 list-decimal space-y-1 pl-5 text-muted" {...p} />,
          li: (p) => <li className="text-muted" {...p} />,
          strong: (p) => <strong className="font-semibold text-text" {...p} />,
          blockquote: (p) => (
            <blockquote className="my-3 border-l-2 border-accent/50 bg-surface-2 px-3 py-2 text-muted" {...p} />
          ),
          code: (p) => (
            <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-accent" {...p} />
          ),
          table: (p) => (
            <div className="my-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm" {...p} />
            </div>
          ),
          th: (p) => (
            <th className="border border-border bg-surface-2 px-2 py-1 text-left font-medium text-text" {...p} />
          ),
          td: (p) => <td className="border border-border px-2 py-1 text-muted" {...p} />,
          a: (p) => <a className="text-accent underline" {...p} />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
