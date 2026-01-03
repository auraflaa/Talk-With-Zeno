import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize from 'rehype-sanitize';

interface MarkdownMessageProps {
    content: string;
    className?: string;
}

/**
 * Safely renders markdown content with support for:
 * - Headers (# ## ###)
 * - Bold (**text**) and italic (*text*)
 * - Code blocks (```code```) and inline code (`code`)
 * - Lists (ordered and unordered)
 * - Links ([text](url))
 * - Blockquotes (> text)
 * - Tables
 * - Line breaks
 * - Strikethrough (~~text~~)
 * - Task lists
 */
export const MarkdownMessage: React.FC<MarkdownMessageProps> = ({ content, className = '' }) => {
    return (
        <div className={`markdown-content ${className}`}>
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeRaw, rehypeSanitize]}
                components={{
                    // Headers
                    h1: ({ node, ...props }) => <h1 className="text-2xl font-bold mb-2 mt-4 first:mt-0" {...props} />,
                    h2: ({ node, ...props }) => <h2 className="text-xl font-bold mb-2 mt-3 first:mt-0" {...props} />,
                    h3: ({ node, ...props }) => <h3 className="text-lg font-semibold mb-2 mt-3 first:mt-0" {...props} />,
                    h4: ({ node, ...props }) => <h4 className="text-base font-semibold mb-1 mt-2 first:mt-0" {...props} />,
                    h5: ({ node, ...props }) => <h5 className="text-sm font-semibold mb-1 mt-2 first:mt-0" {...props} />,
                    h6: ({ node, ...props }) => <h6 className="text-xs font-semibold mb-1 mt-2 first:mt-0" {...props} />,
                    
                    // Paragraphs
                    p: ({ node, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props} />,
                    
                    // Lists
                    ul: ({ node, ...props }) => <ul className="list-disc list-inside mb-2 space-y-1 ml-4" {...props} />,
                    ol: ({ node, ...props }) => <ol className="list-decimal list-inside mb-2 space-y-1 ml-4" {...props} />,
                    li: ({ node, ...props }) => <li className="mb-1" {...props} />,
                    
                    // Code blocks
                    code: ({ node, inline, className, ...props }: any) => {
                        if (inline) {
                            return (
                                <code className="bg-base-300 dark:bg-base-800 px-1.5 py-0.5 rounded text-sm font-mono" {...props} />
                            );
                        }
                        return (
                            <code className="block bg-base-300 dark:bg-base-800 p-3 rounded-lg overflow-x-auto text-sm font-mono mb-2" {...props} />
                        );
                    },
                    pre: ({ node, ...props }) => <pre className="mb-2" {...props} />,
                    
                    // Links
                    a: ({ node, ...props }) => (
                        <a 
                            className="text-primary hover:underline underline-offset-2" 
                            target="_blank" 
                            rel="noopener noreferrer"
                            {...props} 
                        />
                    ),
                    
                    // Blockquotes
                    blockquote: ({ node, ...props }) => (
                        <blockquote className="border-l-4 border-primary/30 pl-4 my-2 italic text-base-content/80" {...props} />
                    ),
                    
                    // Tables
                    table: ({ node, ...props }) => (
                        <div className="overflow-x-auto my-2">
                            <table className="min-w-full border-collapse border border-base-300" {...props} />
                        </div>
                    ),
                    thead: ({ node, ...props }) => <thead className="bg-base-300 dark:bg-base-800" {...props} />,
                    tbody: ({ node, ...props }) => <tbody {...props} />,
                    tr: ({ node, ...props }) => <tr className="border-b border-base-300" {...props} />,
                    th: ({ node, ...props }) => (
                        <th className="border border-base-300 px-3 py-2 text-left font-semibold" {...props} />
                    ),
                    td: ({ node, ...props }) => (
                        <td className="border border-base-300 px-3 py-2" {...props} />
                    ),
                    
                    // Horizontal rule
                    hr: ({ node, ...props }) => <hr className="my-4 border-base-300" {...props} />,
                    
                    // Images (sanitized)
                    img: ({ node, ...props }) => (
                        <img className="max-w-full h-auto rounded-lg my-2" {...props} />
                    ),
                    
                    // Strong (bold)
                    strong: ({ node, ...props }) => <strong className="font-semibold" {...props} />,
                    
                    // Emphasis (italic)
                    em: ({ node, ...props }) => <em className="italic" {...props} />,
                    
                    // Strikethrough
                    del: ({ node, ...props }) => <del className="line-through opacity-70" {...props} />,
                    
                    // Line breaks
                    br: ({ node, ...props }) => <br {...props} />,
                }}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
};

