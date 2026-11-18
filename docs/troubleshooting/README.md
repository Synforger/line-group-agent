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
- `answer: no reply to send` means the model answered without `<reply>…</reply>`;
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

## The agent does not start

It prints the reason and exits with status 2:

- `missing setting: …` / `… must be a …`: fix the configuration file
- `cannot read the file named by …`: the secret file is missing or unreadable
- `cannot read spend.json`: the spend file is damaged; move it aside (this
  month's figure then starts from 0)
