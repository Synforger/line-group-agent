# The running conversation

Each group has one conversation with the model that goes on from mention to mention,
like a chat you keep open. It is kept in the group's record, so it survives a restart.

## What is added at each mention

- **The first turn of a conversation** carries a short summary of the earlier conversation
  (if there is one), the group's last `recent_message_count` messages (the bot's own replies
  among them, marked as its replies) and the message that mentioned the bot.
- **Every later turn** carries what the group said since the bot's last turn (at most
  `max_catch_up_messages`; the bot's own replies are already in the conversation) and the
  message that mentioned the bot.
- **Either way** a line gives the size of the group (LINE's count of its members, asked again
  after an hour) and the names the group's record knows, so a member who has not spoken yet
  is still counted, for example in a bill split. When LINE does not give the count, the line is
  left out.
- **Either way** the newest [photos](group-tools.md#photos) the group sent since the bot's last
  turn are attached as images.
- The model's answers are kept exactly as the API sent them and sent back unchanged, and the
  conversation is only ever added to. That keeps the start of each request identical to the
  last one, so the API's prompt cache reads it instead of processing it again.

The record keeps the model's thinking blocks, but they are not sent again after their turn:
their signature is tied to the system text and the tool list of the request that made them,
so a changed persona, tool list or version would make the API refuse the whole conversation.
Inside one turn, between a tool call and its result, they are sent back as they came.
This holds for the request that writes a summary too.

A tool call that never got its result (for example when the round limit was reached) is
answered with an error result when the conversation is sent again, so one bad turn does not
stop the group.

## A name in the middle of a message

With `call_name_anywhere` on, a message that holds a call name anywhere (not a LINE mention,
and not at the start of a sentence or the end, which still call the bot as before) is added as a turn too. A name at the start that runs on into the words ("ソラって便利") is read the same way. The
turn tells the model that the message may not be addressed to it, and gives it the tool
`stay_silent`; the model answers when the member asks it to do or answer something ("ソラも〜して"), and stays silent only for talk about it, a reaction or a joke. When the model calls it, nothing is sent to the group and the bot's reply is
not recorded, but the turn stays in the conversation: the bot remembers it read the message,
and the next turn carries only what was said after it. A message that mentions the bot or
has a name at either end is always answered; `stay_silent` is refused there. A turn that calls `stay_silent` together with other tools runs the other tools and answers. A reply written in the same turn as `stay_silent` is sent. The tool is
sent with every request while the setting is on, so the start of the request, and with it the
prompt cache, does not change from one turn to the next.

## The same call twice in one answer

When one answer of the model calls the same tool twice with the same input (the same JSON,
whatever the order of the keys), the second call is not run: it gets a short result that says
it was run once. This holds for every group tool, so a poll is not started twice.

## An answer without `<reply>`

Only the text inside `<reply>…</reply>` is sent. When the model's last answer holds text but no
`<reply>` at all, the agent does not send an error right away: it asks the model once, as a
continuation of the same turn, to write the answer again inside `<reply></reply>`, and sends
the `<reply>` of that answer. The request and the answer stay in the conversation like any
other turn, and the request is a normal request for the budget (it is not made when the month
cannot pay for one, and the group sees the budget text then). An answer with an empty
`<reply></reply>`, with no text, or one cut off in the middle of tool work is not asked again.

When the second answer has no `<reply>` either, the group sees `error_text`, except after a
message that only held the bot's name ([above](#a-name-in-the-middle-of-a-message)): that one
stays silent, because it may not have been meant for the bot.

## How full the conversation is

The amount is the input, cache-read and cache-write tokens of the last answer. As a percent
it is that amount divided by `context_window_tokens` of the [settings file](files.md#settings-file).
The tab list shows both.

## Rolling over

When the conversation gets long, the agent asks the model for a summary and starts a new one
that opens with it:

- After an answer, if the conversation is at least `rollover_percent` full.
- When the group has been quiet for `idle_hours` and the conversation is at least
  `idle_rollover_percent` full (checked at each patrol).

The summary covers what has been decided, what is still open, each person's preferences, the
candidates the bot offered, and what it was asked to do. It is written by one extra request
that may not use tools. The request is not added to the conversation record, but its cost
counts for the group. The summary is saved in the group's journal, and the next mention opens
the new conversation with it. The record keeps going in the same file; a new conversation
starts at a user row whose text begins with `Summary of the conversation so far`. The
generation number is taken from the journal, so it stays right after old rows are deleted.

A conversation that had messages deleted from it is rolled over at once, whatever its size;
see [Deleting messages](deleting.md).

If the summary cannot be made (the group is out of budget, the API fails, the answer is
empty) the conversation carries on and the agent tries again after the next answer or patrol.

## Money

`monthly_budget_usd` (or the configuration's `budget.monthly_limit`) is the limit for the
whole agent. Each known group may spend that limit divided by the number of known groups; a
group with a record or on `allowed_group_ids` is known, and so is any group the bot has
handled a message from. Before a request the agent checks both the whole month and the
group's month, and calls the API only if both can take the most the request may cost. The
first request after a rollover or a long quiet time writes the whole conversation to the
cache, so the estimate counts the write price of `cache_ttl`.
