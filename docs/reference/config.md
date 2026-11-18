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
| `state_dir` | required | Folder for the records and the spend file |
| `tab_name` | required | Name of the conversation record (`a-z`, `0-9`, `-`) |
| `anthropic_api_key_file` | required | File holding the Claude API key |
| `line_channel_secret_file` | required | File holding the channel secret |
| `line_channel_access_token_file` | required | File holding the channel access token |
| `model` | `claude-haiku-5-5` | Claude model id |
| `max_tokens` | `1024` | Longest answer per request (thinking included) |
| `effort` | `low` | `output_config.effort` sent with each request |
| `recent_message_count` | `30` | How many recent group messages go with a mention |
| `max_tool_rounds` | `4` | Tool round trips per mention; the loop stops after this |
| `history_search_limit` | `20` | Most results one history search returns |
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
| `cache_write_per_mtok` / `cache_read_per_mtok` | Per million cache write / read tokens |
| `web_search_per_thousand` | Per 1,000 web searches |
| `long_prompt_threshold_tokens` | Optional. Above this prompt size (input + cache tokens) the `long_*` prices apply to the whole request |
| `long_input_per_mtok`, `long_output_per_mtok`, `long_cache_write_per_mtok`, `long_cache_read_per_mtok` | Optional. Prices for long prompts; a missing one falls back to the normal price |

## `budget`

| Setting | Default | Meaning |
|---|---|---|
| `monthly_limit` | required | Most to spend in a month, in `currency` |
| `currency` | `JPY` | Currency of `monthly_limit` and of the spend file |
| `currency_per_usd` | required | How much one dollar is in `currency` (`1` for `USD`) |
| `estimated_input_tokens_per_request` | `20000` | Prompt size assumed when estimating one request |
| `exhausted_text` | `This month's budget is used up.` | Sent instead of an answer when the budget cannot cover one more |
