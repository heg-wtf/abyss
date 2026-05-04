/**
 * Whisper hallucination filter.
 *
 * Whisper trained heavily on YouTube subtitles, broadcast captions, and
 * podcast intros. When given a silent or very low-signal audio clip, it
 * tends to emit boilerplate from that distribution instead of an empty
 * string. We reject transcripts that match these known phrases so they
 * never reach the LLM as a fake user message.
 */

const HALLUCINATION_FRAGMENTS = [
  // YouTube / streaming subtitle boilerplate (Korean)
  "자막은 설정",
  "자막 제공",
  "자막 by",
  "구독과 좋아요",
  "구독 좋아요",
  "좋아요와 구독",
  "다음 영상",
  "이 영상을 시청",
  "시청해주셔서",
  "시청해 주셔서",
  "광고를 포함",
  "광고가 포함",
  // News/broadcast hallucinations (Korean)
  "MBC 뉴스",
  "KBS 뉴스",
  "SBS 뉴스",
  "YTN 뉴스",
  "KBS입니다",
  "MBC입니다",
  "뉴스데스크",
  // English equivalents
  "subscribe to my channel",
  "thanks for watching",
  "subtitles by",
  "captions by",
];

/**
 * True when the transcript is almost certainly a Whisper hallucination of
 * subtitle/intro boilerplate from a silent or low-signal clip.
 */
export function isLikelyWhisperHallucination(text: string): boolean {
  if (!text) return true;
  const trimmed = text.trim();
  if (!trimmed) return true;

  const lower = trimmed.toLowerCase();
  for (const fragment of HALLUCINATION_FRAGMENTS) {
    if (lower.includes(fragment.toLowerCase())) return true;
  }

  // Very short transcripts (<= 1 char of meaningful content) are almost
  // never legitimate intent. Reject "...", "어", ".".
  const stripped = trimmed.replace(/[\s.!?。…ㅏ-ㅣ]/g, "");
  if (stripped.length <= 1) return true;

  return false;
}
