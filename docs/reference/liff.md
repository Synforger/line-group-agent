# The LIFF pages

With a LIFF app configured the agent serves two pages that open inside LINE: the voting page
for a poll and the [itinerary page](#the-itinerary-page) for the trip itinerary. Both read the
same settings and the same checks (see [What the agent promises](#what-the-agent-promises)).

## The voting page

With a LIFF app configured, a poll card does not carry a button per option. It lists the
options with their counts and has one button, **開いて投票**, that opens a page inside LINE.
There a vote is a tap that paints the option, grows its bar and shows who voted for what, and
**nothing is posted to the talk**. Without a LIFF app the poll cards work as described in
[Polls](group-tools.md#polls) and none of this exists.

### What the page shows

- The question, a line saying how to vote, and one row per option: a bar filled to the
  option's share of the members who voted, its count, and the display names of the members who
  picked it.
- The options the viewer picked are painted in the accent colour with a check mark and a
  border, so the state does not depend on colour alone.
- A poll with one pick moves the vote when another option is pressed, and pressing the option
  already picked changes nothing. A poll with several picks (a date poll too) switches an
  option on and off with each press. A closed poll is shown and takes no press.
- The page reads the poll when it is opened and after each press, from the answer to the press
  itself. It does not refresh on a timer: open it again to see other members' votes.
- It is made for a phone's width and reads in LINE's dark appearance.

Votes made on the page and votes made by pressing a button of an older card land in the same
poll, and the bot's `poll_results` reads both.

## The itinerary page

The [trip itinerary](group-tools.md#trip-itinerary) opens as a calendar from the card the bot
sends (**予定表を開く**). The page only shows the plan; to change it, tell the bot in the talk.

- At the top the trip's name and its dates, and a tab for each day (`11/23(月) 1日目`, or
  `1日目` when the first day is not set). The tab of today is chosen when the trip is on
- Each day is a vertical time axis from an hour before its first item to an hour after its
  last, with a line every half hour. An item is a band as long as its time (an hour when it
  has no end); items that overlap stand side by side. A line shows the time now on the day of
  today
- Items without a time are listed at the top of their day
- Tapping an item opens its details: its time, the place with a link to a map search, the
  note and the link
- An earlier memo (see the itinerary) is folded under "前のメモ". The page reads the plan when
  it is opened, with the 更新 button and when it comes back to the front after half a minute;
  it does not refresh on a timer
- It is made for a phone's width and follows the light and dark appearance

The page's address is `https://liff.line.me/<liff_id>/itinerary?i=<link id>` and opens
`https://<your-host>/liff/itinerary`, below the endpoint URL of the LIFF app, so no new setting
is needed. The link id is made for each group's itinerary from 128 random bits and kept in its
`itinerary.json`; the group's id is never in an address.

| Request | Body | Answer |
|---|---|---|
| `GET /liff/itinerary` | none | the page: one HTML file, no group content |
| `POST /liff/api/itinerary` | `{"i": "<link id>"}` | the plan |

The plan is `{"title", "start_date", "legacy_text", "days": [{"day", "label", "date", "unscheduled": [item], "scheduled": [item with "start_min", "end_min", "bottom_min", "column", "columns"], "axis": {"start_min", "end_min"} or null}]}`,
where an item is `{"title", "start", "end", "place", "map_url", "note", "url"}`. No item id,
member id or group id is in it. The request goes through the same checks as the voting page's:
the ID token, the limits on failed verifies and on a member's requests, the link id's lookup
and the member's place in the group; a link of another group, an unknown link and a member who
is not in the group all give the same **403**.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `liff_id` | none | The LIFF ID of your LIFF app (`<number>-<letters>`) |
| `login_channel_id` | none | The channel ID of the LINE Login channel the LIFF app belongs to |
| `liff_max_requests_per_user_per_minute` | `60` | Requests one member may make to the page's API in a minute |
| `liff_max_body_bytes` | `1024` | Largest request body the page's API accepts |
| `liff_max_failed_verifies_per_minute` | `30` | Verifies LINE may refuse in a minute, over all requests, before the agent stops asking |
| `liff_max_failed_verifies_per_source_per_minute` | `10` | The same, for each source address (the last address of `X-Forwarded-For`, which the proxy in front appends) |

Set `liff_id` and `login_channel_id` together; with neither, the page and its API answer 404
and poll cards keep their buttons. A poll made before the settings were added has no link and
keeps working through its card.

## Setting it up

1. In the [LINE Developers console](https://developers.line.biz/console/), create a **LINE
   Login** channel under the **same provider** as the Messaging API channel. (A member's id
   is the same in both only within one provider; the agent compares it with the group's
   members.)
2. On the Login channel's **LIFF** tab add an app: **Endpoint URL**
   `https://<your-host>/liff/`, scope `openid`, size as you like (Full suits it). Copy the
   LIFF ID.
3. Make `https://<your-host>/liff/` and `https://<your-host>/liff/api/` reach the same
   address as the webhook (`http://127.0.0.1:8790`), by the same reverse proxy or tunnel.
4. Put the LIFF ID in `liff_id` and the Login channel's ID in `login_channel_id`, and
   restart.

The card's button opens `https://liff.line.me/<liff_id>?p=<link id>`. The link id is made for
each poll from 128 random bits; the group's id is never in an address.

## What the agent promises

The page itself, `GET /liff/`, is one HTML file with its script and styles inside, and holds
no group content. All content comes from `POST /liff/api/…`:

| Request | Body | Answer |
|---|---|---|
| `POST /liff/api/poll` | `{"p": "<link id>"}` | the poll |
| `POST /liff/api/vote` | `{"p": "<link id>", "option": <number>}` | the poll after the vote |

`option` counts from 0, in the order of the card. The poll is
`{"question", "kind", "multiple", "is_closed", "voter_count", "options": [{"label", "count", "voters": [names], "mine"}]}`.
No member id or group id is in it.

Each request must carry the member's LINE **ID token** as `Authorization: Bearer <token>`.
Before it gives anything, the agent:

1. asks LINE Login to verify the token (`POST https://api.line.me/oauth2/v2.1/verify` with
   `client_id` set to `login_channel_id`) and checks the audience, the issuer and the expiry
   itself; the token's `sub` is the member. A token that fails is **401**. Failed verifies
   are counted over the last minute, in all (`liff_max_failed_verifies_per_minute`) and for
   each source address, the last address of `X-Forwarded-For` (the one the proxy in front
   appends; earlier ones are written by the caller)
   (`liff_max_failed_verifies_per_source_per_minute`; without the header only the count of
   all is kept). While either is at its limit the agent does not ask LINE and the answer is
   **429**, so a flood of made-up tokens cannot use up the channel's calls to LINE. A verify
   that succeeds, a request without a token and a LINE outage (503) are not counted; the log
   holds the number of the limit that was hit, never an address;
2. counts the member's requests against `liff_max_requests_per_user_per_minute` (also **429**);
3. looks the poll up by its link id and checks that its group is one the agent answers in;
4. asks LINE whether the member is in that group (the group member profile; the answer is
   remembered for five minutes). A poll that does not exist, a group that is not allowed and
   a member who is not in the group all give the same **403**, so an id's existence is not
   revealed.

While the limit for all is reached a real member is refused too (429) until the failures are
a minute old. `X-Forwarded-For` is set by your reverse proxy; one that passes a client's own
header through lets that client pick a new source each time, and then only the limit for all
holds.

When LINE cannot be reached for steps 1 or 4 the answer is **503**, not a refusal of the
member. A body over `liff_max_body_bytes` is **413**, a body that is not the request above
**400**. Every answer says `Cache-Control: no-store`; a refusal is a bare status with a
one-word error and no detail. The log holds statuses only, never a token, a link id, a name
or what was sent.

The page may not be cached, sends no `Referer`, and sets names and options only as text.
