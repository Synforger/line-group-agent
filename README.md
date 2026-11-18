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
- **Looks things up.** Web search and web page reading (server-side tools of the
  Claude API) plus a search over the group's own record.
- **Says only what it means to say.** Only the text the model puts inside
  `<reply>…</reply>` is sent to the group; its working notes never are.
- **Stays within a monthly budget.** Each answer's cost is counted from the API's
  usage figures. Before calling the API, the agent checks that this month's spend
  plus the most one answer can cost stays within your limit; if not, it replies
  with a fixed line instead.
- **Treats the group as data.** Group messages are handed to the model in an
  envelope and are never read as instructions; the agent has no tool that can
  book, pay or send anything outside the group.

## How it works

```
LINE group ──▶ LINE Platform ──https──▶ your HTTPS entry ──▶ line-group-agent (127.0.0.1:8790)
                                                               │  POST /line/webhook
                                                               │  1. size cap, signature check, 200 at once
                                                               │  2. allowed group? record the message
                                                               │  3. mentioned? ask the Claude API ──▶ web search / web fetch
                                                               │                                  └─▶ search_history (local record)
                                                               └─ 4. reply (or push if the reply token expired)
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
| Cache write (5 minutes) / cache read | $0.125 / $0.01 per million tokens |
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
- The estimate is a guard, not a bill. Also set a spend limit on the API key's
  workspace in the Claude Console.
- A reply uses LINE's reply token and is free. When the model takes longer than
  the token lives (about a minute), the agent sends the answer as a push message
  instead, which counts against your account's monthly message quota.

## Files it writes

All under `state_dir`:

| Path | What |
|---|---|
| `groups/<groupId>/messages.jsonl` | Every text message of the group, one JSON object per line (time, message id, user id, display name when LINE gives it, text). Append only |
| `conversations/<tab_name>.jsonl` | What was sent to the model and what it answered, one row per line, for a chat client to show read-only |
| `spend.json` | This month's spend: `{"month", "spent", "limit", "currency", "updated_at"}`, rewritten whole each time |

Formats are in [`docs/reference/files.md`](docs/reference/files.md).

## Documentation

- Setup (LINE channel, running as a service): [`docs/setup/`](docs/setup/README.md)
- Configuration and file formats: [`docs/reference/`](docs/reference/README.md)
- Troubleshooting: [`docs/troubleshooting/`](docs/troubleshooting/README.md)
- Contributing: [`docs/internals/`](docs/internals/README.md)

## License

Apache-2.0 ([`LICENSE`](LICENSE)). Dependencies are listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md); vulnerability reports go
through [`SECURITY.md`](SECURITY.md).
