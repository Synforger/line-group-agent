# Configuration

One JSON file, passed as `--config <path>`. A relative path in it is read from the
folder that holds the file. Settings are not taken from environment variables.

| Setting | Default | Meaning |
|---|---|---|
| `host` | `127.0.0.1` | Address to listen on. Keep it on loopback |
| `port` | `8790` | Port to listen on |
| `max_body_bytes` | `1048576` | Largest webhook body accepted; larger ones get 413 |
| `allowed_group_ids` | `[]` | Groups whose messages are recorded and answered. Others are dropped and their id is logged |
| `persona_file` | required | Text file that starts the system text (who the bot is) |
| `state_dir` | required | Folder for the records, the summaries, the spend files and the tab list |
| `settings_file` | `settings.json` next to this file | The [settings file](files.md#settings-file) a settings screen writes: monthly budget, context window and rollover thresholds. Read again whenever it changes; a missing file means the defaults |
| `tabs_file` | `<state_dir>/tabs.json` | Where the [tab list](files.md#tabsjson) for a chat client is written |
| `tab_name` | ignored | Older versions named one conversation record with it. Each group now has its own record (`conversations/g-<groupId>.jsonl`), so the setting is no longer used; a file left under the old name is not touched |
| `anthropic_api_key_file` | required | File holding the Claude API key |
| `line_channel_secret_file` | required | File holding the channel secret |
| `line_channel_access_token_file` | required | File holding the channel access token |
| `model` | `claude-haiku-5-5` | Claude model id |
| `max_tokens` | `1024` | Longest answer per request (thinking included) |
| `effort` | `low` | `output_config.effort` sent with each request |
| `cache_ttl` | `1h` | How long the prompt cache lives: `1h` or `5m`. A one-hour cache costs more to write and keeps a quiet group's conversation cheap to continue; see [Cost](../../README.md#cost) |
| `recent_message_count` | `30` | How many recent group messages open a conversation (the first message after a summary, or the first ever) |
| `max_catch_up_messages` | `200` | Most group messages added to a conversation at one mention (what was said since the bot's last turn); older ones are left out |
| `summary_max_tokens` | `2048` | Longest summary written when a conversation is rolled over |
| `patrol_interval_seconds` | `600` | How often the agent looks over every group: quiet conversations to roll over, group names, the settings file |
| `max_tool_rounds` | `4` | Tool round trips per mention; the loop stops after this |
| `history_search_limit` | `20` | Most results one history search returns |
| `redelivered_answer_window_seconds` | `600` | A mention that LINE redelivers (after a failed delivery) is answered only when it is at most this old; an older one is recorded but not answered. A message already in the record is never handled twice |
| `required_member_user_id` | none | A LINE user id (yours, as shown in LINE Developers). When set, the bot leaves a group that is not in `allowed_group_ids` as soon as it hears from it, unless this user is a member; a group whose membership LINE cannot confirm is left too. Groups that pass are logged with their id, as before |
| `allow_groups_with_required_member` | `false` | With `required_member_user_id` set: a group that user is in counts as allowed (recorded and answered) without being listed. The membership is asked again after an hour, and the bot leaves the group once that user is gone. Every message of such a group is recorded from the moment the bot joins, so tell the group first |
| `web_search` | `{"type": "web_search_20250305", "max_uses": 3}` | Web search tool; `null` turns it off |
| `web_fetch` | `{"type": "web_fetch_20250910", "max_uses": 2, "max_content_tokens": 8000}` | Web page reading tool; `null` turns it off |
| `prices_usd` | required | Prices, below |
| `budget` | required | Monthly limit, below |

The web tool `type`s default to the basic versions, which every model that
supports the tools accepts. Newer versions (`web_search_20260209` and later,
`web_fetch_20260209` and later) filter results with code before they reach the
model; set them here if your model supports them.

## `prices_usd`

All in US dollars. Required unless marked optional.

| Setting | Meaning |
|---|---|
| `input_per_mtok` / `output_per_mtok` | Per million input / output tokens |
| `cache_write_per_mtok` / `cache_read_per_mtok` | Per million cache write (5 minutes) / read tokens |
| `cache_write_1h_per_mtok` | Optional. Per million tokens written to the one-hour cache; twice `input_per_mtok` when missing |
| `web_search_per_thousand` | Per 1,000 web searches |
| `long_prompt_threshold_tokens` | Optional. Above this prompt size (input + cache tokens) the `long_*` prices apply to the whole request |
| `long_input_per_mtok`, `long_output_per_mtok`, `long_cache_write_per_mtok`, `long_cache_read_per_mtok` | Optional. Prices for long prompts; a missing one falls back to the normal price |
| `long_cache_write_1h_per_mtok` | Optional. One-hour cache writes of a long prompt; twice `long_input_per_mtok` when missing |

## `budget`

| Setting | Default | Meaning |
|---|---|---|
| `monthly_limit` | required | Most to spend in a month, in `currency`. The settings file's `monthly_budget_usd` takes its place when it gives one |
| `currency` | `JPY` | Currency of `monthly_limit` and of the spend file |
| `currency_per_usd` | required | How much one dollar is in `currency` (`1` for `USD`) |
| `estimated_input_tokens_per_request` | `20000` | Prompt size assumed when estimating one request |
| `exhausted_text` | `This month's budget is used up.` | Sent instead of an answer when the budget cannot cover one more |
