# Notices, limits and alerts

Besides its answers, the bot sends a few fixed texts, holds each person to a limit, and
tells you when it cannot do its job. The texts come from the configuration file (see
[config.md](config.md)); an empty text is not sent.

## Plain text, and quoting

LINE shows no Markdown, so the bot is told not to use it, and before a reply goes out
the agent also cleans it: a `#` at the start of a line, `**` around words and a `-` or
`*` bullet at the start of a line are turned into plain text (a bullet becomes `・`).
The same goes for the title, line and price of a [card](cards.md).

A reply quotes the message that mentioned the bot, so it is clear who is being answered.
If LINE refuses the quote, the reply is sent without it.

## When no answer could be made

| Case | What the group sees |
|---|---|
| The month's budget cannot cover the answer | `budget.exhausted_text` |
| The Claude API failed | Nothing (and an [alert](#alerts) to you after three failures in a row) |
| Anything else went wrong (the model gave no `<reply>`, ran out of tool rounds, or the agent hit an error) | `error_text` |

## The wait text

When the model's first reply shows that a longer wait is ahead (a web search is under
way and the turn goes on), the agent sends `wait_text` at once through the reply token,
and the real answer follows later as a push message. A push counts against the LINE
account's monthly message quota, so the wait text is sent only when LINE reports at
least `wait_min_push_left` messages left this month. The agent asks LINE for that number
at most once an hour; when LINE does not say, or fewer are left, the wait text is skipped
and the answer goes out as the reply, as usual. An empty `wait_text` turns it off.

## The hourly limit

One person may mention the bot `max_mentions_per_user_per_hour` times in any hour. A
mention over the limit is recorded but not answered. The first time a person passes the
limit, the bot sends `rate_limit_text`; it does not repeat it until that person has been
answered again.

## The introduction

When the bot joins a group it may answer, it sends the text of `intro_file` once, through
the join event's reply token. A group counts when it is on `allowed_group_ids`, or when
`required_member_user_id` is in it and `allow_groups_with_required_member` is on. Without
`intro_file` nothing is sent. The text is recorded as the bot's own message.

## The welcome

When a new member joins a group the bot may answer in, it sends `welcome_text` once through
that event's reply token (so it uses none of the month's push messages). Without
`welcome_text` nothing is sent. The text is the same for every member, and it is recorded as
the bot's own message.

## Alerts

With `alert_user_id` set (or `required_member_user_id`, when that is not), the bot sends
that LINE user one short push message in these cases, and not more than once per kind in
six hours:

- the Claude API failed three calls in a row
- the whole agent's spend this month passed 80% of its limit
- sending a message to LINE failed

The account has to be a friend of that user for the push to arrive.
