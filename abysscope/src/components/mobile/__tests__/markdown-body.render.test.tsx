// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { MarkdownBody } from "../mobile-chat-markdown-body";

describe("MarkdownBody", () => {
  it("renders plain text content as a paragraph", () => {
    const { container } = render(<MarkdownBody content="hello world" />);
    expect(container.textContent).toContain("hello world");
    expect(container.querySelector("p")).not.toBeNull();
  });

  it("renders bold markdown via <strong>", () => {
    const { container } = render(<MarkdownBody content="**bold**" />);
    expect(container.querySelector("strong")).not.toBeNull();
  });

  it("renders fenced code blocks as <pre><code>", () => {
    const { container } = render(
      <MarkdownBody content={"```\nconst x = 1;\n```"} />,
    );
    expect(container.querySelector("pre code")).not.toBeNull();
  });

  it("renders GFM tables (remarkGfm enabled)", () => {
    const md = "| h |\n|---|\n| c |";
    const { container } = render(<MarkdownBody content={md} />);
    expect(container.querySelector("table")).not.toBeNull();
  });

  it("breaks single newlines into <br> (remarkBreaks enabled)", () => {
    const { container } = render(
      <MarkdownBody content={"line one\nline two"} />,
    );
    expect(container.querySelector("br")).not.toBeNull();
  });

  it("renders empty content without throwing", () => {
    const { container } = render(<MarkdownBody content="" />);
    expect(container.firstChild).not.toBeNull();
  });

  it("emits a strikethrough element for ~~text~~ (GFM)", () => {
    const { container } = render(<MarkdownBody content="~~gone~~" />);
    expect(container.querySelector("del")).not.toBeNull();
  });
});
