"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

/**
 * Assistant messages may contain GitHub-flavored markdown (headings,
 * fenced code, lists, links). We share the desktop chat's
 * ``prose prose-sm`` tailwind-typography setup so the typography
 * looks the same on both surfaces. ``break-words`` +
 * ``[overflow-wrap:anywhere]`` keep long URLs / Korean text from
 * blowing past the bubble width on narrow phones.
 */
export const MarkdownBody = React.memo(function MarkdownBody({
  content,
}: {
  content: string;
}) {
  // ``min-w-0`` lets this flex/grid child actually shrink below its
  // content's intrinsic width. ``break-words`` +
  // ``[overflow-wrap:anywhere]`` break long unbreakable strings
  // (URLs, Korean blobs without spaces) instead of pushing the
  // bubble wider. ``<pre>`` blocks get their own ``overflow-x-auto``
  // so a wide code line scrolls within the bubble — never the
  // whole page. Tables get the same treatment.
  return (
    <div className="prose prose-sm dark:prose-invert min-w-0 max-w-full break-words [overflow-wrap:anywhere] text-foreground prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-em:text-foreground prose-li:text-foreground prose-blockquote:text-foreground prose-code:text-foreground prose-a:text-foreground prose-pre:my-2 prose-pre:max-w-full prose-pre:overflow-x-auto prose-pre:rounded-md prose-pre:bg-background/40 prose-pre:p-2 prose-code:break-words prose-img:max-w-full prose-table:block prose-table:max-w-full prose-table:overflow-x-auto prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
      {/* ``remarkBreaks`` turns single ``\n`` into ``<br>`` — without
          it CommonMark collapses single newlines to a space, which
          made schedule bullets and short status replies render as
          one giant run-on paragraph on the phone. ``remarkGfm`` adds
          tables / strikethrough / autolinks so assistant replies
          render the same as on GitHub. */}
      <ReactMarkdown remarkPlugins={[remarkBreaks, remarkGfm]}>
        {content || ""}
      </ReactMarkdown>
    </div>
  );
});
