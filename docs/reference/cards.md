# Cards

When the agent lists two or more candidates (hotels, restaurants, things to do), it
can send them as a row of cards that members swipe sideways. This is a LINE Flex
Message carousel. The agent decides when to use it; there is nothing to configure.

## What a card shows

| Part | Source | Notes |
|---|---|---|
| Picture | `image_url` | Optional. Shown on top, 20:13, tapping it opens the page |
| Name | `title` | Bold. Up to 40 characters |
| Price | `price` | Optional. Up to 20 characters, e.g. `¥2,980〜` |
| Short line | `text` | Up to 60 characters |
| Button 「開く」 | `url` | Opens the page in LINE's browser |

Cards are sent after the reply text, in the same call. A reply can carry one set of
cards, 1 to 10 of them (if the model asks for more than one set, the last counts). The
cards can also be sent without any text. The notification and the talk list show
`候補: <name> / <name> / …` in place of the cards.

## What is checked

The model's request is checked before anything is sent:

- `url` and `image_url` must start with `https://`, hold no space or control
  character, name a host and be at most 1000 characters. Non-ASCII characters are
  percent-encoded first. A card whose `url` fails is dropped; a card whose
  `image_url` fails is sent without its picture
- Text over its limit is cut and ends with `…`; line breaks become spaces
- Cards past the tenth are dropped

## When LINE refuses the cards

A refused message and a refused reply token are both an HTTP 400, so the agent reads
LINE's error message to tell them apart. It never writes that message, the group's
words or an address into its log; only the status.

1. Reply token refused (used or expired): the text and the cards are pushed instead.
   If LINE refuses that push because of the cards, the text is pushed alone.
2. Message refused: the reply is tried once more with the pictures removed.
3. Still refused: the text is sent alone, by push, and the cards are dropped.

Only what was actually delivered is written into the group's record
([files.md](files.md)).
