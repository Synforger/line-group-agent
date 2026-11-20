# Tools for the group

Besides searching the web and the group's record, the bot has a few tools that work on the
group itself. The model decides when to use one, from what a member asks. Each tool keeps its
data in the group's own folder under `state_dir` (see [files.md](files.md)), and counting,
saving and sums are done by the agent in code, not by the model.

## Polls

A member can ask the bot to start a vote ("vote on where to go: Kyoto or Osaka"). The bot
sends a card after its reply: the question and one button per option, up to 10 options of 20
characters each. Pressing a button casts a vote, and what the group sees depends on the kind
of poll (below). The votes are counted by the agent, so a vote costs no model call and no
message.

- **One vote each (the default).** Pressing a button makes LINE show `<option> に投票` in the
  talk as a message of the member who pressed it (the button's display text, which LINE limits
  to 300 characters; an option is at most 20), so everyone sees the press worked and who voted
  for what. The bot adds nothing. Pressing another option moves the vote; pressing the option
  already picked again changes nothing, so a member who presses twice does not lose the vote.
  To take a vote back the member asks the bot ("cancel my vote"): the model calls
  `withdraw_vote`, which removes only the votes of the member whose message it is answering,
  from the newest open poll or the one named by id (`p1`)
- **Several picks (`multiple`).** Each option is its own switch: a press picks it, a second
  press takes it back. LINE shows nothing for such a press, so the bot answers it with one
  line through the press's reply token: `<name>: <the options that member has picked now,
  in the poll's order>`, or `<name>: なし` when none is left (`あなた` stands in for a name LINE
  did not give). The model is not called, the line is not recorded in the group's record and
  it is never pushed: when LINE refuses the reply token the line is dropped and the vote is
  still counted. No display text is set on these buttons
- A mention such as "how is the vote going?" makes the bot read the count (the model reports
  it, and may show it as cards). "Close the vote" ends the poll; a closed poll takes no more
  votes and no answer line. Without an id the newest open poll is meant; polls are numbered
  `p1`, `p2` … in the group, and the newest 50 are kept
- The poll is written into the group's record as one line (`[投票] p1 Where? 1. Kyoto / 2.
  Osaka`), so a later mention can refer to it

A vote is counted only when LINE tells the agent which member pressed the button (the member's
user id). A press that arrives without one cannot be told from another member's press, so it
is not counted, and the agent logs one line saying so.

**With a LIFF app configured** ([the voting page](liff.md)) the card is different: it lists the
options with their counts and has one button, "開いて投票", that opens a page inside LINE. There
a press paints the option, grows its bar and shows who voted for what, and nothing is posted to
the talk, so the display text and the answer line above do not apply. The rules of counting
(one pick moves, several picks switch, a closed poll takes nothing) are the same, and a card
sent before the setting was added keeps working with its buttons.

## Finding a date

When members need to agree on a date, the bot sends a date poll: a card with one button per
candidate date (up to 10). A member presses every date that suits them, and presses again to
take one back; each press is answered with the member's dates so far, like a poll with several
picks (`Aki: 11/23(Sat)、11/25(Mon)`). Counting is the same as for polls: "which day works best?" makes the bot read
each date's count and who marked it, and "close it" ends the poll. The record line starts
with `[日程]`.

The cards use plain buttons; LINE's date picker is not used, because LINE does not say it is
available in group chats.

## Trip itinerary

The group has one itinerary, kept item by item. Each item has a day (1 is the first day of the
trip), an optional start and end time, a title, and an optional place, note and link. The trip
has a name and, when known, the date of its first day. A member tells the bot what to put in
it ("add dinner at 7 on day two") and asks what is in it ("what is the plan?"); the bot adds,
changes and removes one item at a time by its id, so a change never rewrites the rest.

| Tool | What it does |
|---|---|
| `get_itinerary` | Reads the trip, every item with its id grouped by day, and the earlier versions. With `show_card` it also sends the itinerary as a card; with `show_image` as [images](liff.md#the-itinerary-images) |
| `add_itinerary_item` | Adds one item (`day` and `title` are required) |
| `change_itinerary_item` | Changes the fields given for one item; an empty string clears an optional field |
| `remove_itinerary_item` | Removes one item |
| `set_itinerary_trip` | Sets the trip's name and/or the date of its first day |
| `restore_itinerary` | Puts an earlier version back as the current one |

- A time is `HH:MM`, 24-hour, and an end must be later than its start on the same day. A link
  must start with `http://` or `https://`. A field over its length (title 60, place 80, note
  300 characters) is refused, not cut. An itinerary holds at most 150 items and 30 days
- The card shows the next three items (by the first day's date and the time now; without a
  first day, the first three) and one button, **予定表を開く**, that opens the
  [itinerary page](liff.md#the-itinerary-page): the whole plan as a calendar. Without a LIFF
  app there is no page and no card, and the bot gives the plan in its reply
- With `show_image` the plan is also sent as up to three images, drawn like the calendar page
  with every day one under the other (see [the itinerary images](liff.md#the-itinerary-images)).
  The bot is told to use it when a member asks for the plan as an image and when it has just
  finished building the plan. Images count among the three extra messages a reply may carry, and
  the card comes after them. When no image can be made (`public_base_url` is not set, or the
  browser is missing) the card is sent instead
- Every change keeps the state it replaced, the last five of them, in the group's
  `itinerary.json`. `restore_itinerary` puts one back and keeps the state it replaces, so a
  restore can be undone too
- An itinerary written by an earlier version of this program (one plain text) is read as an
  itinerary with no items and that text as an earlier memo. The bot sees the memo with
  `get_itinerary` and turns it into items when asked; the page shows it folded under
  "前のメモ". It is never deleted
- A mention that holds only an itinerary keyword (`itinerary_keywords` in the
  [configuration](config.md), `itinerary` by default; the mention, a call name and
  punctuation around it are ignored) gets the itinerary's card without the model, so it costs
  nothing; without a LIFF app it gets the plan as text. An itinerary with no items gets one
  short line (and the button when an earlier memo is kept). That reply is not recorded as a
  turn. When no itinerary is saved yet, the model answers as for any mention

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

## Reminders

A member can ask the bot to say something to the group at a set time ("tell us to gather at 21:00
the evening before", "remind Aki about the tickets on Friday morning"). At that time the bot
sends the text to the group by itself, without anyone mentioning it. The model sets it with
`set_reminder` (when, what, and optionally the display names of the members to call);
`list_reminders` shows the waiting ones with their ids and how many of the month are used, and
`cancel_reminder` removes one by id.

- **"Set a reminder" alone is enough.** When a member asks for one without saying when or what,
  the model decides both from the conversation and the [itinerary](#trip-itinerary), sets it,
  and says in one line what it set and when. It asks a short question only when it cannot decide
- **The text is sent as it was set**, with no label such as "Reminder:" in front. To call
  members, they are [mentioned](#mentions) before the text: a real LINE mention for a member the
  group's record knows by that name, `@name` as plain text for any other. When LINE refuses the
  mentions (a member who has left the group), the reminder is sent again with `@name` for all
- **Times are in Japan time.** A time given without an offset is taken as Japan time. A time
  that has already passed, or is more than 60 days ahead, is refused
- **A group may have `max_reminders_per_group_per_month` reminders (10 by default) fall due in
  one month.** Each costs one message of the account's monthly allowance, since it goes out as a
  push. A reminder that is cancelled, missed or given up is not counted. Past the limit the call is
  refused and the model tells the members why. It is also refused while LINE reports fewer than
  `wait_min_push_left` messages left this month (the same figure the wait text uses; the figure
  is refreshed with each round below, so it is at most an hour old)
- **A round runs every minute** and sends every reminder whose time has come. A send that fails
  is tried once more at the next round; when that fails too, the reminder is given up and the
  agent logs one line with its id and the status. When the agent was not running at the time, a
  reminder at most 30 minutes late is still sent; an older one is not sent and is logged
- A sent reminder is not written into the group's record

## Photos

A photo a member sends to the group is kept (the agent reads it from LINE as soon as it
arrives, since LINE keeps the content only for a while) and the record gets a line `[写真]` for
it. When the bot is next called, the newest photos sent since its last turn (at most
`max_images_per_turn`, 3 by default) are given to the model together with the group's messages,
so a member can ask "what is this?" about a photo.

- A photo is scaled down before it is kept when its long side is over `max_image_edge_pixels`
  (1568 by default) or its file is large (it is then saved again as JPEG), so a large photo
  costs little. A smaller one is kept as it is
- Photos live in `groups/<groupId>/images/` and, as part of what was sent to the model, in the
  conversation record. A photo is deleted with its message (on request, when unsent, or after
  `retention_days`; see [Deleting messages](deleting.md))
- `max_images_per_turn` set to `0` turns this off: photos are neither kept nor recorded
- Only JPEG, PNG, GIF and WEBP photos are used. Anything else, or a photo LINE no longer gives,
  is still recorded as `[写真]`, without a file

## Locations

- **A place a member shares** (LINE's location message) is recorded as a line
  `[位置] name address (latitude, longitude)`, so the bot can use it when it is next called ("find
  a restaurant near where I just shared")
- **A place the bot recommends** can be sent as a location message after its reply (a map
  card that opens the map when tapped), with a real address and coordinates. One location goes
  out per reply, and it is recorded in the same form

## Mentions

The bot can call a member by name with a real LINE mention, which notifies them. The model writes
`<mention>name</mention>` inside its reply, and the agent sends the reply as a
[text message (v2)](https://developers.line.biz/en/reference/messaging-api/#text-message-v2)
in which that name is a mention of the member.

- **Only a name the group's record holds becomes a mention.** The name must equal, exactly, the
  display name of a member in the last 1000 recorded messages (the name the model sees in the
  conversation). A name that does not match, or that two members share, is sent as the plain name
  without the mark. `<mention>all</mention>` never mentions everyone; it is sent as the word
- **Only when naming someone is needed**: the result of splitting a bill, an answer to the person
  who asked, a reminder. Otherwise the model writes names plainly
- A message holds at most 20 mentions (later marks are plain names), and a reply too long for a
  text v2 message is sent as plain text
- When LINE refuses a reply that has mentions (a mentioned member who has since left the group,
  for example), the agent sends it again as plain text with the names, so the answer still arrives
- The bot's reply is recorded with the marks, as written, so a later deletion of that reply
  still finds it

## Stickers

- **A sticker a member sends** is recorded as `(スタンプ: <keywords>)`, with the keywords LINE
  gives (`(スタンプ)` when it gives none), so the bot can read the mood of the talk. A sticker alone
  never calls the bot, even when it is sent as a reply to one of the bot's messages
- **A sticker the bot sends** goes out after its reply text, through the tool `send_sticker`: the
  model picks one name from the configured list. One sticker per reply, and the model is told to
  use one only when it lightens the mood, not in every reply. It is recorded as
  `(スタンプ: <name>)`
- The list is the setting [`stickers`](config.md): a name for each sticker's LINE package id and
  sticker id. The default has eleven stickers from the sets LINE lets a bot send (the
  [sticker list](https://developers.line.biz/en/docs/messaging-api/sticker-list/)):
  `了解`, `ありがとう`, `おめでとう`, `ごめん`, `笑う`, `楽しみ`, `おやすみ`, `よろしく`, `びっくり`,
  `がんばれ` and `おつかれさま`. `{}` turns the tool off. LINE accepts only the stickers on that
  list, so an id from outside it makes LINE refuse the message

## Quick replies

When the bot asks a question that a tap can answer ("Kyoto or Osaka?"), it can put up to five
buttons under its reply. LINE shows them under the last message and removes them once one is
tapped or someone else writes. A tap sends the option as the tapper's own message, written
`<first call name>、<option>` (for example `Sora、Kyoto`), so it reaches the bot like a typed
call. Without any `call_names` configured, a tap sends the option alone, which does not call
the bot; set a call name when you want the buttons to work. A button shows the first 20
characters of its option.
