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
| The running conversation | Rebuilt from the changed record |

Both files are replaced whole (written to a temporary file, then renamed over the old
one), so a client that shows the record reads it again from the start.

The conversation is then rolled over at once: the model writes a summary and the next
mention opens a new conversation from it. The request for that summary tells the model
not to write what was deleted. A summary written before the deletion is not changed.

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
- the summaries in `groups/<groupId>/journal/`, which are never deleted

The generation number does not depend on the rows that were deleted: it is taken from the
journal.
