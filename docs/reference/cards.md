# Cards

When the agent lists two or more candidates (hotels, restaurants, things to do), it
can send them as a row of cards that members swipe sideways. This is a LINE Flex
Message carousel. The agent decides when to use it. The pictures can be switched off with
[`card_image_lookup`](config.md); there is nothing else to configure.

## What a card shows

| Part | Source | Notes |
|---|---|---|
| Picture | `image_url`, else the page's own | Optional. Shown on top, 20:13, tapping it opens the page. See [Pictures](#pictures) |
| Name | `title` | Bold. Up to 40 characters |
| Price | `price` | Optional. Up to 20 characters, e.g. `¥2,980〜` |
| Short line | `text` | Up to 60 characters |
| Button 「開く」 | `url` | Opens the page in LINE's browser. It is the candidate's own page, see [The page of a card](#the-page-of-a-card) |

Cards are sent after the reply text, in the same call. A reply can carry one set of
cards, 1 to 10 of them (if the model asks for more than one set, the last counts). The
cards can also be sent without any text. The notification and the talk list show
`候補: <name> / <name> / …` in place of the cards.

## The page of a card

The model is told that the `url` of a card is the page of that candidate itself: its official
site, or its own page on a site such as Tabelog, Google Maps, Jalan or Rakuten Travel. A roundup
article, a ranking, a list or a search result page is not one, and two cards never share a
`url`. The agent enforces the last part: a card whose `url` an earlier card already has is
dropped (the log says how many), so the cards left are all different pages.

## Pictures

Web search results seldom hold a picture's address, so the model usually sends a card without
`image_url`. For such a card the agent reads the card's page (`url`) and takes the picture the
page names for itself: its `og:image`, else its `twitter:image` (a relative address is made
absolute against the page). A card that already has an `image_url` is left as the model made
it, and a card whose page names no usable picture stays without one.

A picture is used only when the page is that candidate's page, so that a roundup's cover is
never shown as a shop's photo:

- The page's title (its `og:title`, else its `<title>`) must hold the card's name. Both are
  compared in NFKC form, ignoring case and runs of spaces. The name is the card's `title`
  without the text in brackets (`()`, `（）` and `【】`); the text inside a bracket, such as a
  reading, counts as a name too. Either one found in the page title is enough
- A name of fewer than two characters is not used. A page with no title never matches
- When the same picture address is found for two or more cards, it is given to none of them.
  This does not touch an `image_url` the model wrote

A card that fails either check is sent without a picture; the log says only that no picture was
found, or how many pictures were not used.
 The lookup runs after the
model has finished and before the cards are sent, for all cards at once; when a page is slow
the answer waits for it for at most two seconds.

The page is fetched with these limits, and the card is sent without a picture when any of them
stops the lookup (nothing else is affected, and the log says only that no picture was found):

- `https` only, on the default port, with no user name in the address. The picture's own
  address must be `https` too (the same checks as `image_url` below)
- Public addresses only. The name is resolved first and the page is not fetched unless every
  address it gives is public: loopback, private, link-local, carrier-grade NAT, multicast and
  reserved addresses are refused, and so is an IPv6 address that wraps one of them. The
  connection is then made to the address that was checked (the name is still sent, and the
  certificate is still checked against it), so the name cannot answer differently the second
  time
- Up to three redirects, each target checked the same way
- Two seconds for a page, redirects and reading included
- Only the first 256 KB of a page is read, and only a page that is HTML (or says nothing
  about its type)

With `card_image_lookup` set to `false` no page is fetched and cards keep exactly what the
model gave them.

## What is checked

The model's request is checked before anything is sent:

- `url` and `image_url` must start with `https://`, hold no space or control
  character, name a host and be at most 1000 characters. Non-ASCII characters are
  percent-encoded first. A card whose `url` fails is dropped; a card whose
  `image_url` fails is sent without its picture
- Text over its limit is cut and ends with `…`; line breaks become spaces
- A card whose `url` an earlier card has is dropped
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
