# Deleting messages and keeping records

## On request

A member can ask the bot to delete something ("delete what I said about the hotel").
The model then searches the group's record and deletes the matches with its
`delete_messages` tool. It may delete only:

- messages written by the person who asked, and
- the bot's own earlier replies.

Other members' messages are never deleted, and neither is the message that made the
request. One request deletes at most `history_search_limit` messages, newest first. The
tool tells the model how many were deleted, not what they said.

## When a member unsends a message

When a member takes a message back in LINE (unsend), the agent deletes it the same way.

## What is deleted, and from where

| Place | What happens |
|---|---|
| The group's record (`messages.jsonl`) | The messages are removed |
| The conversation record (`conversations/g-<groupId>.jsonl`) | Where the messages appear in what was sent to the model, their text is replaced by `[deleted]`; a reply of the bot that was deleted is replaced the same way. The model's thinking blocks are removed from its answers |
| The summaries (`groups/<groupId>/journal/`) | A summary that holds the text of a deleted message word for word is rewritten by the model without it, and the other parts are kept. See below |
| The photo files (`groups/<groupId>/images/`) | The files of deleted photo messages are removed, and in the conversation record the caption and the image of a deleted photo are replaced by `[deleted]` |
| The running conversation | Rebuilt from the changed record |

Both files are replaced whole (written to a temporary file, then renamed over the old
one), so a client that shows the record reads it again from the start.

The conversation is then rolled over at once: the model writes a summary and the next
mention opens a new conversation from it. The request for that summary tells the model
not to write what was deleted.

### Summaries written before the deletion

A summary the model wrote earlier may quote the message. Once the deletion is done (after
the answer that made it, or at once for an unsend), the agent looks for the deleted text,
word for word, in every summary of the group. A summary that holds it is rewritten by one
extra request that may not use tools: the model is given the summary and the deleted texts and
asked to take that content out and keep the rest. The summary waiting to open the next
conversation, and the first row of a running conversation that opened with it, are changed the
same way. The request counts against the group's budget.

- If the request cannot be made (the budget is gone, or the API fails), or the rewritten text
  still holds the deleted text, the agent replaces the text by `[deleted]` itself, so the
  content is gone either way
- A message of fewer than 4 characters is not looked for, since it would match anything
- The deleted texts are kept in memory only until this is done, never in a file. If the agent is
  stopped in between, the summaries keep what they quoted
- What the model wrote in its own words about the message (not word for word) is not found

Things to know:

- Only the agent's own records change. The message stays in the LINE chat itself, and a
  reply of the bot cannot be unsent from there.
- The words in which the model itself described a deleted message are not searched for.
  They go away with the rollover, not before.
- The message that asked for the deletion stays in the record.

## How long the records are kept

Once a day (at the first patrol after a day has passed) the agent deletes the messages of
the group record and the rows of the conversation record that are older than
`retention_days` (30 by default). Two things are kept:

- the running conversation: its rows, and the group messages written since it began, are
  not deleted however old they are; they go with the conversation after it is rolled over
- the summaries in `groups/<groupId>/journal/`, which are never deleted by age (one is
  only rewritten to take out a deleted message)

The generation number does not depend on the rows that were deleted: it is taken from the
journal.
