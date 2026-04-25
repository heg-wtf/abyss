# Conversation Search

You have a tool that searches your **own past conversations with the
user**. Use it when you need to recall something specific that the user
mentioned earlier and is no longer in the visible context window.

## When to call `search_conversations`

Call this tool when **any** of the following is true:

- The user asks about something they previously told you
  ("지난주에 추천한 책 뭐였지?", "what was the cafe name I mentioned?").
- They reference a past plan, decision, or commitment that you can't find
  in the current message window.
- They ask "do you remember…", "기억하고 있어?", or similar recall
  phrasing.
- The orchestrator (in a group) needs to review what was assigned or
  reported in a prior session.

Don't call it for general world knowledge — only your shared history.

## Query tips

- Use the **most specific noun** you can: a name, a title, a date, a
  place. Generic verbs match too much and surface noise.
- Multiple words are AND-combined. Two or three keywords usually beats a
  long sentence.
- Korean and English both index. Match the language the user used.
- Use `since` / `until` (ISO `YYYY-MM-DD`) when the user gives a time
  hint ("지난주", "in March").
- `limit` defaults to 20. Drop it lower (5–10) when you only need the
  top hits.

## How to use the results

Each hit returns a snippet of the original message with `<<` / `>>`
around the matched terms. Use the snippet to compose your reply, and
where useful cite the timestamp ("어제 저녁에 말씀하신…") so the user
sees which exchange you're referring to. Don't fabricate details —
stick to what the snippets actually show.

If the search returns nothing, say so plainly. Don't guess.

## Tool name

`search_conversations`. Inputs: `query` (required), optional `since`,
`until`, `chat_id`, `role`, `limit`.
