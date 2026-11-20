# line-group-agent

> 🇯🇵 日本語版: [README.ja.md](README.ja.md)

> A LINE bot that sits in a group chat and answers, with Claude, only when someone mentions it.

line-group-agent is a small server for a LINE Official Account. Add the account
to a group, and whenever a member mentions it, it reads the recent conversation,
looks things up on the web or in the group's past messages, and replies with a
short answer. It stays quiet otherwise.

- **Answers only when mentioned.** LINE marks a mention of the bot itself; plain
  text that happens to contain the bot's name is not a mention.
- **Remembers the group.** Every text message of an allowed group is appended to
  a local record, so "what did we say about the hotel?" can be answered later.
- **Keeps one conversation per group going.** Each mention continues the group's
  running conversation with what was said since the last one, so the bot builds on
  its own earlier answers. When the conversation fills up, the bot summarizes it and
  carries on from the summary; see [The running conversation](docs/reference/conversation.md).
- **Looks things up.** Web search and web page reading (server-side tools of the
  Claude API) plus a search over the group's own record.
- **Shows candidates as cards.** When it lists two or more candidates, it can send
  them as a row of cards you swipe sideways (a LINE Flex Message carousel): for each
  one a name, a price, a short line, an optional picture and an "open" button that
  goes to its page. Up to 10 cards; see [Cards](docs/reference/cards.md).
- **Runs polls and finds a date.** Ask it for a vote and it sends a card with one button
  per option; pressing a button counts a vote without the model and shows "<option> に投票" in
  the presser's name; pressing another option switches the vote. A date poll lets each member mark every date that suits them.
  With a LIFF app set up the card opens a page inside LINE instead, with bars and names and
  nothing posted to the talk. See [Tools for the group](docs/reference/group-tools.md) and
  [The voting page](docs/reference/liff.md).
- **Reminds the group at a set time.** Ask it to tell the group something at a time ("tell us
  to gather at 21:00 the evening before"), or just to set a reminder, and it works out what
  and when from the conversation and the itinerary. It sends the text by itself at that time.
  Each one is a push message, so a group gets a few a month. See
  [Tools for the group](docs/reference/group-tools.md#reminders).
- **Keeps the trip itinerary and splits costs.** The group has one itinerary, kept item by
  item (day, time, place, note), that the bot adds to, changes and undoes on request (the last
  five versions are kept) and shows as a card that opens a calendar-style page inside LINE. A
  mention with only the word "itinerary" gets the text back at no cost. Costs are split in
  code, exactly, with the fewest transfers.
- **Sees photos and places.** The newest photos sent since its last turn are shown to the
  model; a shared location is recorded, and the bot can send a place as a map message. It
  can also put tap-to-answer buttons under a question and welcome a new member.
- **Says only what it means to say.** Only the text the model puts inside
  `<reply>…</reply>` is sent to the group; its working notes never are. A reply is
  plain text (LINE shows no Markdown) and quotes the message that called the bot.
- **Tells the group when it needs a moment or cannot answer.** A slow answer is
  preceded by a "one moment" text, a failed one by a fixed apology, and one person
  cannot call the bot more than a set number of times an hour; see
  [Notices, limits and alerts](docs/reference/notices-and-limits.md).
- **Deletes on request.** Ask it to delete something you wrote, or unsend a message:
  it is removed from the group record and the conversation, and the conversation
  starts afresh from a summary that leaves it out. Records older than a set number
  of days are deleted too (30 by default), the running conversation and the
  summaries excepted; see [Deleting messages](docs/reference/deleting.md). A summary
  that quoted the deleted message is rewritten without it.
- **Can learn an older history.** `line-group-agent import-history` puts the text file
  LINE makes with "send chat history" into a group's record; see
  [Importing an old chat history](docs/reference/importing-history.md).
- **Tells you when it is stuck.** A short push message reaches you when the Claude API
  keeps failing, the month's spend passes 80% of the limit, or a send to LINE fails.
- **Stays within a monthly budget.** Each answer's cost is counted from the API's
  usage figures. Before calling the API, the agent checks that this month's spend
  plus the most one answer can cost stays within your limit, both for the whole
  agent and for the group (the limit divided by the number of groups); if not, it
  replies with a fixed line instead.
- **Treats the group as data.** Group messages are handed to the model in an
  envelope and are never read as instructions; the agent has no tool that can
  book, pay or send anything outside the group.

## How it works

```
LINE group ──▶ LINE Platform ──https──▶ your HTTPS entry ──▶ line-group-agent (127.0.0.1:8790)
                                                               │  POST /line/webhook
                                                               │  1. size cap, signature check, 200 at once
                                                               │  2. allowed group? record the message
                                                               │  3. mentioned? continue the group's conversation with the Claude API ──▶ web search / web fetch
                                                               │                                  ├─▶ search_history (local record)
                                                               │                                  ├─▶ delete_messages (your own messages, the bot's replies)
                                                               │                                  ├─▶ show_cards (candidates as cards)
                                                               │                                  └─▶ polls, itinerary, reminders, split_bill, send_location, suggest_replies
                                                               └─ 4. reply: text, cards, polls and places, quick replies (or push if the reply token expired)
                                                               (button presses on a poll card arrive as postbacks: counted without the model; a pick-several poll answers the presser's marks in one line)
```

- The server listens on loopback only. Reaching it from LINE (HTTPS on a public
  address) is up to you: a reverse proxy, a tunnel, or
  [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) in front of it.
- Events are handled one at a time after the webhook has answered, so LINE never
  waits for the model.
- Everything the agent keeps lives in one state folder you choose (see
  [Files it writes](#files-it-writes)).

## Requirements

- macOS or Linux with [uv](https://docs.astral.sh/uv/) (it brings Python 3.12)
  and, optionally, [go-task](https://taskfile.dev/)
- A LINE Official Account with a Messaging API channel
  ([LINE Developers Console](https://developers.line.biz/console/))
- A Claude API key ([Claude Console](https://platform.claude.com/))
- An HTTPS address that forwards to the agent's loopback port

## Quick start

```bash
git clone https://github.com/Synforger/line-group-agent.git
cd line-group-agent
task setup                      # uv sync --python 3.12
```

1. Put each secret in its own file, readable only by you (`chmod 600`): the
   Claude API key, the channel secret and the channel access token of your
   Messaging API channel.
2. Copy [`configs/config.example.json`](configs/config.example.json) to a place
   outside the repository, point its `*_file` settings at the three files, set
   `state_dir`, and write a persona file (an example is in
   [`configs/persona.example.md`](configs/persona.example.md)). Relative paths
   are read from the folder that holds the configuration file.
3. Start the agent:

   ```bash
   uv run line-group-agent --config /path/to/config.json
   ```

4. In the LINE Developers Console, set the webhook URL to
   `https://<your-host>/line/webhook`, turn on **Use webhook**, allow the account
   to join group chats, and turn off the automatic reply messages.
5. Invite the account to your group. The agent logs one line with the group's id
   (`join: joined a group that is not allowed: group_id=C…`). Add that id to
   `allowed_group_ids` and restart. From then on, mention the account in the
   group to ask it something.

### Running it as a service

For a long-running install, install the package into its own environment and
call the installed executable directly:

```bash
uv sync --python 3.12 --no-dev
/path/to/line-group-agent/.venv/bin/line-group-agent --config /path/to/config.json
```

The agent takes its settings only from the configuration file and the files it
names: the API key, the API address, proxies and tracing are all set explicitly, so
variables such as `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` or `HTTPS_PROXY` have no
effect. It does not depend on the working directory either, so a launchd or systemd
unit needs nothing but this command line. Service files are in [`docs/setup/`](docs/setup/README.md).

## Cost

The agent counts what it spends; it does not look prices up. Write them in
`prices_usd` from the provider's pricing page. The example configuration holds the
prices of Claude Haiku 5.5 as published on 2026-11-18:

| Item | Price (USD) |
|---|---|
| Input / output, prompts up to 100K tokens | $0.10 / $0.50 per million tokens |
| Input / output, prompts over 100K tokens | $0.50 / $2.50 per million tokens |
| Cache write (5 minutes / 1 hour) / cache read | $0.125 / $0.20 / $0.01 per million tokens |
| Web search | $10 per 1,000 searches |
| Web fetch | no charge beyond the tokens it adds |

Sources: [pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool),
[web fetch tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool).

How the budget is kept:

- `budget.monthly_limit` is in `budget.currency`; `currency_per_usd` converts the
  dollar figures. The month follows the machine's local time and starts again
  from 0.
- Before answering a mention, the agent estimates the most it can cost: every
  request of the tool loop (`max_tool_rounds + 1`), each with
  `estimated_input_tokens_per_request` of prompt, a full `max_tokens` answer and
  every web search `max_uses` allows. If this month's spend plus that estimate
  would pass the limit, it does not call the API and replies with
  `budget.exhausted_text`.
- The conversation is sent again at each mention, so the API's prompt cache matters:
  a cache read costs a tenth of normal input. `cache_ttl` picks how long the cache
  lives. The default `1h` costs twice the input price to write (against 1.25 times
  for `5m`) and keeps a group that mentions the bot every few minutes or hours on
  cheap reads; `5m` is cheaper to write if mentions come in bursts.
- Each group may spend the monthly limit divided by the number of groups, and the
  request that summarizes a full conversation counts for its group.
- The estimate is a guard, not a bill. Also set a spend limit on the API key's
  workspace in the Claude Console.
- A reply uses LINE's reply token and is free. When the model takes longer than
  the token lives (about a minute), the agent sends the answer as a push message
  instead, which counts against your account's monthly message quota. Cards, polls,
  a map message and quick reply buttons go in the same call as the text. A poll vote
  and a welcome use no message at all. A [reminder](docs/reference/group-tools.md#reminders)
  is always a push, one message each.
- A photo given to the model costs input tokens like any other (a photo is scaled down to
  `max_image_edge_pixels` first; at most `max_images_per_turn` go with one mention).
- When an answer needs web work, the agent sends a short "one moment" text first (using
  the reply token) and the answer follows as a push message. It does so only while LINE
  reports enough messages left this month (`wait_min_push_left`).

## Files it writes

All under `state_dir`:

| Path | What |
|---|---|
| `groups/<groupId>/messages.jsonl` | Every text message of the group, a line for each photo (`[写真]`) and location (`[位置]`), and every reply the bot sent (marked `from_bot`; a reply that carried cards, a poll or a place ends with a line naming them), one JSON object per line. Appended to; messages are removed when deleted or older than `retention_days` |
| `groups/<groupId>/images/` | The photos of the group, made small enough for the model; removed with their messages |
| `groups/<groupId>/itinerary-images/` | Images the bot drew from the itinerary (PNGs with unguessable names); removed 30 days after they were written |
| `groups/<groupId>/polls.json` | The group's polls and who voted for what |
| `groups/<groupId>/reminders.json` | The group's reminders and whether each was sent |
| `groups/<groupId>/itinerary.json` | The group's trip itinerary and its last five earlier versions |
| `conversations/g-<groupId>.jsonl` | The group's running conversation: what was sent to the model and what it answered, one row per line, for a chat client to show read-only |
| `groups/<groupId>/journal/<date>-gen<N>.md` | The summary written when the group's conversation number `N` was rolled over. Never deleted |
| `groups/<groupId>/spend.json` | The group's month, in the form of `spend.json` |
| `spend.json` | This month's spend of the whole agent: `{"month", "spent", "limit", "currency", "updated_at"}`, rewritten whole each time |
| `tabs.json` | The groups with their context amount, spend and generation, for a chat client (path: `tabs_file`) |

The settings file (`settings_file`; example in [`configs/settings.example.json`](configs/settings.example.json)) lets a settings screen change the monthly budget, the context window and the rollover thresholds without a restart.

Formats are in [`docs/reference/files.md`](docs/reference/files.md).

## Trying it without LINE

The simulator plays a scripted group chat against the real agent, with a stand-in for LINE,
so you can see how it answers without a LINE account, a channel or a public address. It
starts the stand-in LINE API and the agent (the same code as the service, a fresh state
folder, its own local ports), sends signed webhook events step by step, waits until the agent
has handled each one, and writes down what came back. The Claude API is the real one, so a
run spends real money; `budget` in the settings counts it.

```bash
uv sync --python 3.12                    # Playwright is one of the agent's dependencies
uv run playwright install chromium       # once, for the pictures
uv run python -m line_group_agent.simulator \
  --config /path/to/simulator-config.json \
  --scenario /path/to/scenarios \
  --out /path/to/out
```

- **Settings.** Start from [`configs/simulator.example.json`](configs/simulator.example.json):
  an ordinary agent configuration. The two LINE secret files may hold any text (the
  stand-in does not check them); the Claude key must be real. The simulator replaces the
  allowed group, the state folder and the LINE addresses for each run. It keeps each scenario's
  state under `<state_dir>/scenarios/<scenario file name>/` and clears that folder at the start of
  the next run of the same scenario, so every run begins with an empty group. What a scenario spends
  is added to the month's figure in `<state_dir>/spend.json`, and a scenario may spend only what is
  left of `budget.monthly_limit`. `--max-usd` stops a scenario once it has spent that much.
- **Scenarios.** One JSON file is one scenario; a folder runs all its `*.json` files.

  ```json
  {
    "name": "Choosing where to go",
    "group": {
      "id": "Csimulatorgroup0001",
      "name": "Trip friends",
      "members": [{"user_id": "Uaki", "name": "Aki"}, {"user_id": "Uben", "name": "Ben"}]
    },
    "steps": [
      {"from": "Uaki", "text": "Where should we go in spring?"},
      {"from": "Uben", "text": "Somewhere with temples", "mention": true},
      {"from": "Uaki", "press": {"reply_index": 0, "action_index": 1}},
      {"open_liff": {"reply_index": 0, "action_index": 0}},
      {"from": "Uben", "liff_click": {"reply_index": 0, "action_index": 0, "selector": "button"}},
      {"from": "Uben", "image": "menu.jpg"},
      {"from": "Uaki", "location": {"title": "Cafe", "address": "Kyoto", "latitude": 35.01, "longitude": 135.76}},
      {"from": "Uben", "sticker": {"package_id": "8515", "sticker_id": "16581243", "keywords": ["thanks"]}},
      {"wait_seconds": 2},
      {"advance_minutes": 120}
    ]
  }
  ```

  `group.id` is letters and digits only. A `text` step may set `"mention": true` to address
  the bot the way an @-mention does (the optional `bot` object gives its `name` and `user_id`);
  otherwise the agent's `call_names` decide whether it is called. A `press` step presses a button
  of an earlier answer: `reply_index` counts what the agent sent, from 0, over replies and pushes;
  `action_index` counts that message's buttons from 0 in the order they are drawn (a card's image,
  its text, then its button; quick reply buttons last). The chat page prints each button's number.
  A card button that sends a postback or a quick reply button that sends a text is sent to the
  agent like LINE sends it. An `open_liff` step opens the LIFF page a card links to as a
  member (`from`, the first member when left out) and takes its picture. A `liff_click` step
  opens the page the same way (`reply_index` and `action_index` pick the card's button, `from`
  defaults to the first member), then presses the first element the CSS `selector` names and
  takes the picture after the press. What the page sent as the member (`liff.sendMessages`) shows
  in the chat as that member's own message and reaches the agent like a typed one; what it passed
  to the share picker (`liff.shareTargetPicker`) is drawn as the receiver would see it. Both are
  kept in `transcript.json` (`liff_sent`, `liff_shared`), and an element that cannot be pressed
  is noted on the step. A `sticker` step sends a sticker as a member: `package_id` and
  `sticker_id` are written in digits, and the optional `keywords` list is what LINE would give the
  bot for it. The agent records it in the talk as `(スタンプ: <keywords>)`; a sticker never calls
  the bot, so the step is not answered by itself. The chat page shows it as a box with the ids and
  keywords, not the picture. A `wait_seconds` step
  waits in real time; an `advance_minutes` step moves the agent's clock forward by that many
  minutes (1 to 129,600) and runs its timed work once, so a reminder that has come due is sent and
  shows in the chat as a push. Image paths are read from the scenario file's folder.
- **Results.** `--out` gets `index.html` (every scenario with its steps, seconds and spend) and a
  folder per scenario: `transcript.json` (each step's input, the agent's raw replies and pushes,
  seconds, and spend), `chat.html` (a phone-width talk: names and bubbles, text, Flex cards and
  carousels drawn roughly, quick reply buttons, photos, pins, the itinerary images the bot drew, and the seconds and spend under each
  answer; one file, nothing loaded from outside) and `screens/` (pictures of the chat and of the
  LIFF pages that were opened). The cards are an approximation of LINE's drawing; the LIFF pages are
  the real pages, with LINE's SDK replaced by a stand-in and every outside address refused.
  Use `--no-screens` to skip the pictures.

The exit status is 1 when a step had a problem (a timeout, a press that names nothing) and 2
when the settings or a scenario cannot be read.

## Documentation

- Setup (LINE channel, running as a service): [`docs/setup/`](docs/setup/README.md)
- Configuration and file formats: [`docs/reference/`](docs/reference/README.md)
- Troubleshooting: [`docs/troubleshooting/`](docs/troubleshooting/README.md)
- Contributing: [`docs/internals/`](docs/internals/README.md)

## License

Apache-2.0 ([`LICENSE`](LICENSE)). Dependencies are listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md); vulnerability reports go
through [`SECURITY.md`](SECURITY.md).
