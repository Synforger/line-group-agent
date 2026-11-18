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
- **Either way** the newest [photos](group-tools.md#photos) the group sent since the bot's last
  turn are attached as images.
- The model's answers are kept exactly as the API sent them and sent back unchanged, and the
  conversation is only ever added to. That keeps the start of each request identical to the
  last one, so the API's prompt cache reads it instead of processing it again.

A tool call that never got its result (for example when the round limit was reached) is
answered with an error result when the conversation is sent again, so one bad turn does not
stop the group.

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
