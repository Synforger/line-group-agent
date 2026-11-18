# Troubleshooting

## The webhook verification in the LINE console fails

- **Symptom**: **Verify** reports an error; the log shows `webhook: bad or missing signature`.
- **Cause**: the channel secret file does not hold this channel's secret.
- **Fix**: copy the **Channel secret** from **Basic settings** again, write it to
  the file without a trailing space, and restart.

## The bot never answers

- Check the log for `events: dropped events of a group not allowed: group_id=…`:
  add that id to `allowed_group_ids` and restart.
- The bot answers only a real mention (pick the account from the mention list).
  Typing its name as plain text is not a mention.
- Someone may have passed `max_mentions_per_user_per_hour`: the log says `answer: a member
  passed the hourly limit; not answered`.
- `answer: no reply to send` means the answer was empty and `error_text` is empty too, or the
  bot chose to stay silent on a message that only held its name. A model that answers without
  `<reply>…</reply>` is asked once to write it again inside the tags; when it still does not,
  make the persona less wordy, or raise `max_tokens` if answers are cut off.
- `answer: API refused the request (status 401)` means the API key file is wrong.

## The bot replies "This month's budget is used up."

This month's spend plus the most one answer may cost would pass
`budget.monthly_limit`. Check `spent` in `spend.json` under `state_dir`. Raise the limit,
or lower `max_tool_rounds`, `max_tokens` or `estimated_input_tokens_per_request`
to make one answer's estimate smaller.

## The bot replies "This month's budget is used up." for one group only

Each group may spend the monthly limit divided by the number of groups. Check `spent` and
`limit` in `groups/<groupId>/spend.json`, or the group's `spend` in the tab list. Raise
`monthly_budget_usd` in the settings file (no restart needed), or note that adding a group
lowers every group's share.

## The settings file seems to be ignored

`settings: cannot use settings.json (…); keeping the previous values` in the log means the
file is not valid JSON or a value is of the wrong kind or out of range (percentages are
above 0 and at most 100, `context_window_tokens` is a whole number above 0). The previous
values stay until the file is fixed. A missing file means the defaults.

## Answers arrive as a separate message instead of a reply

`reply: the reply token was refused; sending by push instead` means the answer
took longer than LINE keeps a reply token (about a minute). The answer is still
sent, as a push message, which counts against the account's monthly message
quota. Fewer `max_uses` on the web tools make answers faster.

## The bot says "Something went wrong"

That is `error_text`: the model gave no `<reply>…</reply>` even after being asked once more
(on a message that only held the bot's name it stays silent instead), used up its tool rounds
(`max_tool_rounds`) or the agent hit an error; the log has one `answer:` line with the
reason. When the Claude API itself fails, the bot stays silent and logs
`model: API call failed` or `model: API refused the request (status …)`.

## The wait text arrives, then the answer a while later

That is intended: the answer needed web work, so the wait text took the reply token and the
answer is a push message. Raise `wait_min_push_left` (or empty `wait_text`) to keep pushes
for answers only.

## Pressing a poll button does nothing

The press arrives as a postback event. The log tells which case it is:

- `poll: a press came without a user id; not counted`: LINE did not say who pressed, and the
  agent cannot count a vote it cannot attribute. Votes work only when LINE puts the member's
  user id in the event
- `poll: a vote was unchanged`: the member pressed the option they had already picked in a
  one-pick poll; the vote stays (ask the bot to withdraw it)
- `poll: a vote was ignored`: the poll is closed, or its card is older than the polls kept (the
  newest 50)
- No line at all: the group is not in `allowed_group_ids`, or the webhook is not receiving
  postback events

## The bot does not see a photo

- `image: LINE did not give the content of a photo`: LINE gives a message's content for a
  limited time and only to the account the message was sent to; check the channel access token
- `image: a photo could not be used`: only JPEG, PNG, GIF and WEBP files are read
- `max_images_per_turn` is `0` (photos are then not kept at all), or the photo was sent before
  the bot's last turn (only the newest ones since then are shown)

## The quick reply buttons do not call the bot

A tap sends `<first call name>、<option>`; set `call_names` so the message starts with a name
the bot answers to. Without one, a tap sends the option alone.

## The agent does not start

It prints the reason and exits with status 2:

- `missing setting: …` / `… must be a …`: fix the configuration file
- `cannot read the file named by …`: the secret file is missing or unreadable
- `cannot read intro_file`: the introduction file named in the configuration is missing
- `cannot read spend.json`: the spend file is damaged; move it aside (this
  month's figure then starts from 0)
