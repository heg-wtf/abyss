/**
 * Streaming sentence chunker for TTS.
 *
 * LLM responses arrive token-by-token. We accumulate text and emit complete
 * sentences as soon as they cross both:
 *   - a sentence-terminator boundary (`.`, `!`, `?`, `。`, `！`, `？`)
 *   - a minimum length floor (avoids reading "1.", "Mr.", abbreviations).
 *
 * Code blocks (fenced ``` ... ```) are skipped — they read terribly out loud
 * and break Voicebox prosody. Whatever lives inside a code fence is buffered
 * and discarded on flush.
 */

const TERMINATOR_CHARS = new Set([".", "!", "?", "。", "！", "？"]);
const MIN_SENTENCE_LEN = 12;
const FENCE = "```";

export interface ChunkerOptions {
  minSentenceLength?: number;
  /** Skip text inside fenced code blocks (default: true). */
  skipCodeBlocks?: boolean;
}

export class SentenceChunker {
  private buffer = "";
  private inCodeBlock = false;
  private readonly minLength: number;
  private readonly skipCode: boolean;

  constructor(options: ChunkerOptions = {}) {
    this.minLength = options.minSentenceLength ?? MIN_SENTENCE_LEN;
    this.skipCode = options.skipCodeBlocks ?? true;
  }

  push(chunk: string): string[] {
    if (!chunk) return [];
    this.buffer += chunk;
    return this.drain();
  }

  flush(): string[] {
    const sentences = this.drain();
    const tail = this.buffer.trim();
    this.buffer = "";

    if (!tail) return sentences;
    if (this.inCodeBlock && this.skipCode) {
      this.inCodeBlock = false;
      return sentences;
    }
    sentences.push(tail);
    return sentences;
  }

  private drain(): string[] {
    const out: string[] = [];

    while (this.buffer.length > 0) {
      // Inside a code block: drop everything up to the closing fence.
      if (this.skipCode && this.inCodeBlock) {
        const closeIdx = this.buffer.indexOf(FENCE);
        if (closeIdx === -1) return out;
        this.buffer = this.buffer.slice(closeIdx + FENCE.length);
        this.inCodeBlock = false;
        continue;
      }

      // Find the next opening fence and the next emittable sentence boundary.
      const fenceIdx = this.skipCode ? this.buffer.indexOf(FENCE) : -1;
      const sentenceEnd = this.findEmittableSentenceEnd(fenceIdx);

      // Fence opens before any emittable sentence.
      if (fenceIdx !== -1 && (sentenceEnd === -1 || fenceIdx < sentenceEnd)) {
        const before = this.buffer.slice(0, fenceIdx).trim();
        if (before.length > 0) {
          out.push(before);
        }
        this.buffer = this.buffer.slice(fenceIdx + FENCE.length);
        this.inCodeBlock = true;
        continue;
      }

      if (sentenceEnd === -1) return out;

      const sentence = this.buffer.slice(0, sentenceEnd).trim();
      if (sentence.length > 0) out.push(sentence);
      this.buffer = this.buffer.slice(sentenceEnd).replace(/^\s+/, "");
    }

    return out;
  }

  /**
   * Walk terminators in order, returning the index *after* the consecutive
   * terminator run that produces a slice meeting `minLength`. Returns -1 when
   * no such cut is possible yet.
   *
   * `fenceIdx` (>=0 when an unentered fence is queued) caps how far we look.
   */
  private findEmittableSentenceEnd(fenceIdx: number): number {
    const cap = fenceIdx === -1 ? this.buffer.length : fenceIdx;
    let i = 0;
    while (i < cap) {
      if (!TERMINATOR_CHARS.has(this.buffer[i])) {
        i++;
        continue;
      }
      // Consume a run of consecutive terminators.
      let end = i + 1;
      while (end < cap && TERMINATOR_CHARS.has(this.buffer[end])) end++;
      const slice = this.buffer.slice(0, end).trim();
      if (slice.length >= this.minLength) return end;
      // Too short — keep scanning for a later terminator that yields a long
      // enough prefix.
      i = end;
    }
    return -1;
  }
}
