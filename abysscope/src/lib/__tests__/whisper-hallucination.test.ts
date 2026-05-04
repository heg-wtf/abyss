import { describe, expect, it } from "vitest";
import { isLikelyWhisperHallucination } from "@/lib/whisper-hallucination";

describe("isLikelyWhisperHallucination", () => {
  it("flags YouTube subtitle boilerplate", () => {
    expect(
      isLikelyWhisperHallucination("자막은 설정에서 선택하실 수 있습니다.")
    ).toBe(true);
    expect(
      isLikelyWhisperHallucination(
        "자막 제공 및 자막 제공 및 광고를 포함하고 있습니다."
      )
    ).toBe(true);
    expect(
      isLikelyWhisperHallucination("구독과 좋아요 부탁드립니다")
    ).toBe(true);
    expect(
      isLikelyWhisperHallucination("이 영상을 시청해 주셔서 감사합니다")
    ).toBe(true);
  });

  it("flags broadcast intros", () => {
    expect(isLikelyWhisperHallucination("MBC 뉴스 김철수입니다")).toBe(true);
    expect(isLikelyWhisperHallucination("뉴스데스크입니다")).toBe(true);
  });

  it("flags English youtuber boilerplate", () => {
    expect(
      isLikelyWhisperHallucination("Thanks for watching this video!")
    ).toBe(true);
    expect(
      isLikelyWhisperHallucination("Please subscribe to my channel")
    ).toBe(true);
  });

  it("flags empty/whitespace strings", () => {
    expect(isLikelyWhisperHallucination("")).toBe(true);
    expect(isLikelyWhisperHallucination("   ")).toBe(true);
    expect(isLikelyWhisperHallucination("...")).toBe(true);
  });

  it("flags single-character transcripts", () => {
    expect(isLikelyWhisperHallucination("어")).toBe(true);
    expect(isLikelyWhisperHallucination(".")).toBe(true);
  });

  it("passes legitimate Korean speech", () => {
    expect(isLikelyWhisperHallucination("안녕하세요, 오늘 날씨 어때요")).toBe(
      false
    );
    expect(
      isLikelyWhisperHallucination("최근 작업 보고해줘")
    ).toBe(false);
    expect(
      isLikelyWhisperHallucination(
        "Profitics 수익화 진행 상황 어떻게 되고 있어"
      )
    ).toBe(false);
  });

  it("passes legitimate English speech", () => {
    expect(isLikelyWhisperHallucination("Hello, how are you today")).toBe(
      false
    );
    expect(
      isLikelyWhisperHallucination("What is the status of the deployment")
    ).toBe(false);
  });
});
