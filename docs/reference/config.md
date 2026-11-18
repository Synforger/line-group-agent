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
| `alert_user_id` | `required_member_user_id` | A LINE user id that gets a short push message when the agent cannot do its job; see [Alerts](notices-and-limits.md#alerts). Without it (and without `required_member_user_id`) nothing is sent |
| `intro_file` | none | Text file whose content is sent when the bot joins a group it may answer in; see [The introduction](notices-and-limits.md#the-introduction). Unset: no introduction. A file that cannot be read stops the agent at start |
| `welcome_text` | none | Text sent when a new member joins a group the bot may answer in; see [The welcome](notices-and-limits.md#the-welcome). Empty or unset: no welcome. It is recorded as one of the bot's own messages |
| `help_file` | none | Text file sent as is when a mention holds nothing but one of `help_keywords` (the mention itself removed, surrounding punctuation ignored). The model is not called, so it costs nothing, and the list is not recorded as a turn. Unset: the keywords are answered like any mention. A file that cannot be read stops the agent at start |
| `help_keywords` | `["help"]` | The words that ask for `help_file`, compared whole and case-insensitively |
| `itinerary_keywords` | `["itinerary"]` | The words that ask for the saved [trip itinerary](group-tools.md#trip-itinerary): a mention that holds only one of them (compared whole and case-insensitively, the mention, a call name and punctuation ignored) gets the itinerary as it is, without the model. With no itinerary saved, the model answers |
| `call_names` | `[]` | Names that call the bot without a LINE mention: a text message that starts or ends with one of them (any case, spaces and punctuation such as `、` `!` `?` around it ignored) is answered like a mention. A Latin name must not run on into more letters. Empty: only mentions call the bot |
| `call_name_anywhere` | `false` | With `call_names` set: a text message that holds a call name anywhere else (not a mention, and not at its start or end) is read by the model too, which answers only when the message is meant for it and otherwise stays silent: nothing is sent, but the turn is kept in the conversation. A Latin name does not count inside a longer word (`Sora` in `Soraya`). The help and itinerary keywords do not apply to such a message, and a person over `max_mentions_per_user_per_hour` is skipped without being told. See [A name in the middle of a message](conversation.md#a-name-in-the-middle-of-a-message). `false`: only mentions and names at either end call the bot |
| `error_text` | `Something went wrong, so I could not answer. Please try again in a bit.` | Sent when no answer could be made for a reason other than the budget or the API failing. Empty: nothing is sent |
| `wait_text` | `Looking that up, one moment.` | Sent first when the answer will take a while, and the answer follows as a push message. Empty: never sent |
| `wait_min_push_left` | `20` | The wait text is sent only when LINE reports at least this many messages left this month (0 or more) |
| `max_mentions_per_user_per_hour` | `20` | Most mentions of the bot one person gets answered in an hour (1 or more) |
| `rate_limit_text` | `You have asked a lot in the last hour. Please try again a little later.` | Sent the first time a person passes the limit. Empty: nothing is sent |
| `retention_days` | `30` | Group messages and conversation rows older than this are deleted once a day, except the running conversation's; the summaries are kept. See [Deleting messages](deleting.md) (1 or more) |
| `max_images_per_turn` | `3` | Most photos given to the model at one mention (the newest ones the group sent since the bot's last turn). `0` turns photos off: they are neither kept nor recorded. See [Photos](group-tools.md#photos) |
| `max_image_edge_pixels` | `1568` | A photo whose long side is longer is scaled down to this before it is kept (64 or more) |
| `card_image_lookup` | `true` | A card the model sends without a picture is given the `og:image` (else `twitter:image`) of its own page, read with the limits in [Cards](cards.md#pictures): `https` and public addresses only, two seconds a page, the first 256 KB. `false`: no page is fetched for a card |
| `liff_id` | none | The LIFF ID of the app that opens the [voting page](liff.md) from a poll card. Set with `login_channel_id`; without both, poll cards keep their buttons and the page does not exist |
| `login_channel_id` | none | The channel ID of the LINE Login channel that LIFF app belongs to; its ID tokens are verified against it |
| `liff_max_requests_per_user_per_minute` | `60` | Most requests one member may make to the voting page's API in a minute (1 or more) |
| `liff_max_body_bytes` | `1024` | Largest request body the voting page's API accepts; larger ones get 413 (1 or more) |
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
