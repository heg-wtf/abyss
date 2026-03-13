"""Evaluation tests for group orchestrator quality.

These tests call the real Claude API and are NOT part of normal CI.
Run manually:

    uv run pytest tests/evaluation/test_group_orchestrator_quality.py -v

Tests verify that the orchestrator CLAUDE.md instructions produce correct behavior:
- Clarification questions for ambiguous missions
- Direct task decomposition for clear missions
- Proper @mention delegation to team members
- Escalation vs direct answers for member questions
"""

from __future__ import annotations

import pytest

from cclaw.claude_runner import run_claude_one_shot

# --- Test fixtures ---

TEAM_CONFIG = {
    "name": "dev_team",
    "orchestrator": "dev_lead",
    "members": ["coder", "tester"],
}

ORCHESTRATOR_SYSTEM_PROMPT = """You are the orchestrator of a development team.

## Team Members

### @coder_bot
- personality: Senior developer who writes clean code
- role: Write code and implement features
- goal: Clean, working code

### @tester_bot
- personality: QA engineer focused on quality
- role: Write tests and verify quality
- goal: Bug-free code

## Rules
1. If the mission is ambiguous, ask clarifying questions BEFORE breaking it into tasks
2. Analyze the mission and break it into tasks
3. Delegate tasks to members via @mention
4. Reallocate on failure or direction change
5. Synthesize results and report to the user

## Shared Workspace
Results go to: groups/dev_team/workspace/
"""


async def _ask_orchestrator(message: str) -> str:
    """Send a message to orchestrator and get response."""
    prompt = f"{ORCHESTRATOR_SYSTEM_PROMPT}\n\nUser message: {message}"
    response = await run_claude_one_shot(
        prompt=prompt,
        model="haiku",
    )
    return response


# ===========================================================================
# 9-1: Orchestrator clarification quality
# ===========================================================================

CLARIFICATION_CASES = [
    # (user_input, should_ask_clarification)
    ("크롤러 만들어줘", True),
    ("뭔가 만들어줘", True),
    ("앱 하나 만들자", True),
    ("쿠팡에서 노트북 카테고리 상품명/가격 CSV 크롤링해줘", False),
    ("Python으로 2048 게임 만들어줘. pygame 사용. 테스트 포함.", False),
]

CLARIFICATION_INDICATORS = ["?", "확인", "어떤", "무엇", "어디", "which", "what", "how"]
DELEGATION_INDICATORS = ["@coder_bot", "@tester_bot"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input,should_clarify",
    CLARIFICATION_CASES,
    ids=[c[0][:30] for c in CLARIFICATION_CASES],
)
async def test_orchestrator_clarification(user_input: str, should_clarify: bool):
    """Orchestrator asks clarifying questions for ambiguous missions."""
    response = await _ask_orchestrator(user_input)
    response_lower = response.lower()

    has_clarification = any(ind in response_lower for ind in CLARIFICATION_INDICATORS)
    has_delegation = any(ind in response for ind in DELEGATION_INDICATORS)

    if should_clarify:
        assert has_clarification or "?" in response, (
            f"Expected clarification question for '{user_input}', got: {response[:200]}"
        )
    else:
        assert has_delegation, (
            f"Expected @mention delegation for '{user_input}', got: {response[:200]}"
        )


# ===========================================================================
# 9-2: Orchestrator task decomposition quality
# ===========================================================================

DECOMPOSITION_CASES = [
    # (mission, expected_mentions)
    ("크롤러 만들고 테스트해줘", ["@coder_bot", "@tester_bot"]),
    ("코드만 짜줘. 간단한 Hello World Python 스크립트.", ["@coder_bot"]),
    ("테스트만 작성해줘. 기존 scraper.py에 대해.", ["@tester_bot"]),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mission,expected_mentions",
    DECOMPOSITION_CASES,
    ids=[c[0][:30] for c in DECOMPOSITION_CASES],
)
async def test_orchestrator_decomposition(mission: str, expected_mentions: list[str]):
    """Orchestrator delegates to correct bots via @mention."""
    response = await _ask_orchestrator(mission)

    for mention in expected_mentions:
        assert mention in response, (
            f"Expected {mention} in response for '{mission}', got: {response[:200]}"
        )

    # Should not mention bots that aren't needed
    all_bots = {"@coder_bot", "@tester_bot"}
    unexpected = all_bots - set(expected_mentions)
    for bot in unexpected:
        assert bot not in response, (
            f"Unexpected {bot} in response for '{mission}', got: {response[:200]}"
        )


# ===========================================================================
# 11: Orchestrator escalation vs direct answer
# ===========================================================================

ESCALATION_CASES = [
    # (member_question, should_escalate_to_user)
    ("@dev_lead_bot CSV 인코딩은 UTF-8로 하면 될까요?", False),
    ("@dev_lead_bot Python 버전은 3.11 이상이면 되나요?", False),
    ("@dev_lead_bot 쿠팡 로그인 계정 정보가 필요합니다.", True),
    ("@dev_lead_bot 예산이 얼마나 되나요? 유료 API를 써야 할 것 같은데.", True),
]

ESCALATION_INDICATORS = ["사장님", "사장", "user", "확인", "결정", "필요합니다"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,should_escalate",
    ESCALATION_CASES,
    ids=[c[0][:30] for c in ESCALATION_CASES],
)
async def test_orchestrator_escalation(question: str, should_escalate: bool):
    """Orchestrator escalates to user only when it cannot answer directly."""
    prompt = (
        f"{ORCHESTRATOR_SYSTEM_PROMPT}\n\n"
        f"A member bot asks you: {question}\n"
        "If you can answer this technical question directly, answer the member. "
        "If this requires the user's decision (credentials, budget, etc.), "
        "escalate to the user."
    )
    response = await run_claude_one_shot(prompt=prompt, model="haiku")

    has_escalation = any(ind in response for ind in ESCALATION_INDICATORS)
    has_member_answer = "@coder_bot" in response or "@tester_bot" in response

    if should_escalate:
        assert has_escalation or "user" in response.lower(), (
            f"Expected escalation for '{question[:40]}', got: {response[:200]}"
        )
    else:
        # Should answer directly to the member, not escalate
        assert not has_escalation or has_member_answer, (
            f"Expected direct answer for '{question[:40]}', got: {response[:200]}"
        )
