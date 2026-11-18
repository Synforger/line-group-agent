# Roadmap — Synforger/line-group-agent

> A personal project. This page says what works today, what may come next, and what is not planned.

## Works today

- Receives LINE webhooks on loopback only: one endpoint, a body size cap, the signature checked on the raw body before anything is read, and an answer of 200 before any work
- Keeps every text message of the allowed groups in a local, append-only record; events of other groups are dropped, and only their group id is logged
- Answers only when the bot itself is mentioned, with Claude: the web (search and page reading) and a search over the group's record
- Keeps one running conversation per group: each mention adds what was said since the last turn, the conversation is rebuilt from its record after a restart, and a full or long-quiet conversation is summarized and continued from the summary (thresholds from a settings file that can change while it runs)
- Sends only the text inside `<reply>…</reply>`, one answer per mention, made plain (LINE shows no Markdown), quoting the message that called the bot, by reply token, falling back to a push when the token has expired
- Says a fixed text when it needs a moment (before a slow answer, while LINE reports pushes to spare) or cannot answer, holds each person to a number of mentions an hour, and introduces itself when it joins a group it may answer in
- Deletes messages on request (`delete_messages`) and when a member unsends one, from the group record and the conversation, and starts the conversation afresh from a summary that leaves them out; deletes records older than a set number of days, keeping the running conversation and the summaries
- Sends the operator a short push message when the Claude API keeps failing, the month's spend passes 80% of its limit, or a send to LINE fails
- Shows candidates as a carousel of cards (Flex Message): name, price, a short line, an optional picture and an "open" button each, up to 10 cards, sent after the reply text; the cards are written into the group's record so "the second one" can be followed up
- Runs polls (a card with one button per option; a press is counted by the agent without the model; a one-pick poll shows the pick in the presser's name and a second press of the same button keeps the vote, a pick-several poll answers the presser's marks in one line; `withdraw_vote` takes a vote back) and date polls (each member marks every date that suits them), counts and closes them on request; with a LIFF app set up, a card opens a voting page inside LINE (bars, names, nothing posted to the talk)
- Keeps the group's trip itinerary as text, replaced whole on request with the last five versions kept, and returns it at no cost to a mention that is only an itinerary keyword
- Splits costs in code: whole yen, each member's share and balance, and the fewest transfers
- Reads photos: the newest ones since its last turn are shown to the model, scaled down first; records shared locations; can send a place as a map message
- Puts tap-to-answer buttons under a question, and welcomes a new member with a fixed text
- Rewrites a summary that quoted a message once that message is deleted
- Imports an old LINE chat history file into a group's record (`import-history`)
- Keeps a conversation record per group, a tab list and a monthly spend file (overall and per group) that a chat client can show read-only
- Stops calling the API, with a fixed reply, when one more answer could pass the monthly limit of the whole agent or of the group (the limit divided by the number of groups)
- Uses a one-hour prompt cache by default (five minutes is a setting)

## May come next

- Small in-app pages (LIFF) such as a shared itinerary
- Messages the bot sends without being mentioned (push)

## Not planned

- Booking, paying or any action outside the group: the agent only looks things up and answers
- Access to anything on the host other than its own state folder and the files its configuration names
- Authentication inside the server beyond LINE's signature: exposing the port is the job of the HTTPS entry in front of it (see [SECURITY.md](SECURITY.md))

## Bug reports / feature requests

- Security issues: [SECURITY.md](SECURITY.md)
- Everything else: GitHub Issues (pull requests welcome). Responses are best effort.
