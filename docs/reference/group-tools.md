# Tools for the group

Besides searching the web and the group's record, the bot has a few tools that work on the
group itself. The model decides when to use one, from what a member asks. Each tool keeps its
data in the group's own folder under `state_dir` (see [files.md](files.md)), and counting,
saving and sums are done by the agent in code, not by the model.

## Polls

A member can ask the bot to start a vote ("vote on where to go: Kyoto or Osaka"). The bot
sends a card after its reply: the question and one button per option, up to 10 options of 20
characters each. Pressing a button casts a vote and the bot says nothing back, so a vote costs
no message and adds no noise to the group.

- One vote each by default. Pressing another option moves the vote; pressing the same option
  again takes it back. With "pick several" (`multiple`) each option is its own switch
- A mention such as "how is the vote going?" makes the bot read the count (the model reports
  it, and may show it as cards). "Close the vote" ends the poll; a closed poll takes no more
  votes. Without an id the newest open poll is meant; polls are numbered `p1`, `p2` … in the
  group, and the newest 50 are kept
- The poll is written into the group's record as one line (`[投票] p1 Where? 1. Kyoto / 2.
  Osaka`), so a later mention can refer to it

A vote is counted only when LINE tells the agent which member pressed the button (the member's
user id). A press that arrives without one cannot be told from another member's press, so it
is not counted, and the agent logs one line saying so.

## Finding a date

When members need to agree on a date, the bot sends a date poll: a card with one button per
candidate date (up to 10). A member presses every date that suits them, and presses again to
take one back. Counting is the same as for polls: "which day works best?" makes the bot read
each date's count and who marked it, and "close it" ends the poll. The record line starts
with `[日程]`.

The cards use plain buttons; LINE's date picker is not used, because LINE does not say it is
available in group chats.

## Trip itinerary

The group has one itinerary, kept as plain text. A member can tell the bot what to put in it
("add dinner at 7 on day two") and ask what is in it ("what is the plan?"); the bot reads the
saved text, writes the whole new text and saves it. The text uses one heading line per day,
like `1日目 (11/23)`, and may be up to 4,000 characters (what one LINE message holds).

- Every update replaces the whole text and keeps the version it replaced, the last five of
  them, in the group's `itinerary.json`. Putting an older version back is done by hand there
- A mention that holds only an itinerary keyword (`itinerary_keywords` in the
  [configuration](config.md), `itinerary` by default; the mention, a call name and
  punctuation around it are ignored) gets the saved itinerary exactly as it is, without the
  model, so it costs nothing. That reply is not recorded as a turn. When no itinerary is saved
  yet, the model answers as for any mention

## Splitting costs

When members ask to split what they spent ("Aki paid 9,000 for dinner, Sora paid 3,000 for
the train for Aki and Sora, split it"), the bot hands the payments to a tool that does the
sums in code, so the amounts are exact. For each member it gives what they paid, their share
and the difference, and the fewest transfers that settle everyone (a "who pays whom" list).
The model then tells the group.

- Amounts are whole yen. A payment is for everyone or for the members named
- When a payment does not divide evenly among the people it was for, the remaining yen (fewer
  than one per person) are taken by the person who paid, so nobody is asked for a fraction of
  a yen. The result says how many yen that was and the bot is told to mention it
- Nothing is stored: the tool calculates from what the model gives it each time
