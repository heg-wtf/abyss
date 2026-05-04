import { describe, expect, it } from "vitest";
import { SentenceChunker } from "@/lib/sentence-chunker";

describe("SentenceChunker", () => {
  it("emits no sentence until terminator + min length reached", () => {
    const chunker = new SentenceChunker();
    expect(chunker.push("안녕")).toEqual([]);
    expect(chunker.push(" 세상아")).toEqual([]);
    // "안녕 세상아." — 8 chars + period = 9, below min 12, still buffered
    expect(chunker.push(".")).toEqual([]);
    expect(chunker.push(" 한국어 길이 보강.")).toEqual([
      "안녕 세상아. 한국어 길이 보강.",
    ]);
  });

  it("emits multiple sentences from a single chunk", () => {
    const chunker = new SentenceChunker();
    const out = chunker.push("이것은 첫 번째 문장이다. 다음은 두 번째 문장이다. ");
    expect(out).toEqual([
      "이것은 첫 번째 문장이다.",
      "다음은 두 번째 문장이다.",
    ]);
  });

  it("skips fenced code blocks", () => {
    const chunker = new SentenceChunker();
    const out = chunker.push(
      "결과는 다음과 같다. ```python\nprint('hi')\n``` 그리고 끝이다."
    );
    expect(out).toContain("결과는 다음과 같다.");
    expect(out.some((s) => s.includes("print"))).toBe(false);
  });

  it("flush returns trailing fragment even if short", () => {
    const chunker = new SentenceChunker();
    chunker.push("끝없이 흐르는 강물");
    expect(chunker.flush()).toEqual(["끝없이 흐르는 강물"]);
  });

  it("flush discards unfinished code fence", () => {
    const chunker = new SentenceChunker();
    const pushed = chunker.push("앞에 문장이 충분히 길다. ```python\n오픈만 됨");
    const flushed = chunker.flush();
    const combined = [...pushed, ...flushed];
    expect(combined).toEqual(["앞에 문장이 충분히 길다."]);
    expect(combined.some((s) => s.includes("오픈만"))).toBe(false);
  });

  it("does not split on numeric abbreviation when below min length", () => {
    const chunker = new SentenceChunker();
    expect(chunker.push("1.")).toEqual([]);
    expect(chunker.push(" 첫번째 항목입니다.")).toEqual([
      "1. 첫번째 항목입니다.",
    ]);
  });

  it("collapses repeated terminators inside one sentence", () => {
    const chunker = new SentenceChunker();
    const out = chunker.push(
      "정말로 그게 맞는 답인가요?? 그러면 곧장 출발하자고."
    );
    expect(out).toEqual([
      "정말로 그게 맞는 답인가요??",
      "그러면 곧장 출발하자고.",
    ]);
  });

  it("supports english punctuation", () => {
    const chunker = new SentenceChunker();
    const out = chunker.push("Hello world there. Another sentence here. ");
    expect(out).toEqual([
      "Hello world there.",
      "Another sentence here.",
    ]);
  });

  it("can disable code block skipping", () => {
    const chunker = new SentenceChunker({ skipCodeBlocks: false });
    const out = chunker.push("앞 문장 길이가 충분히 길다. ```js\nlet x = 1;\n```");
    expect(out).toContain("앞 문장 길이가 충분히 길다.");
  });
});
