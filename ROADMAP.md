# Roadmap — Synforger/line-group-agent

> A personal project. This page says what works today, what may come next, and what is not planned.

## Works today

- Receives LINE webhooks on loopback only: one endpoint, a body size cap, the signature checked on the raw body before anything is read, and an answer of 200 before any work
- Keeps every text message of the allowed groups in a local, append-only record; events of other groups are dropped, and only their group id is logged
- Answers only when the bot itself is mentioned, with Claude: the web (search and page reading) and a search over the group's record
- Keeps one running conversation per group: each mention adds what was said since the last turn, the conversation is rebuilt from its record after a restart, and a full or long-quiet conversation is summarized and continued from the summary (thresholds from a settings file that can change while it runs)
- Sends only the text inside `<reply>…</reply>`, one answer per mention, by reply token, falling back to a push when the token has expired
- Shows candidates as a carousel of cards (Flex Message): name, price, a short line, an optional picture and an "open" button each, up to 10 cards, sent after the reply text; the cards are written into the group's record so "the second one" can be followed up
- Keeps a conversation record per group, a tab list and a monthly spend file (overall and per group) that a chat client can show read-only
- Stops calling the API, with a fixed reply, when one more answer could pass the monthly limit of the whole agent or of the group (the limit divided by the number of groups)
- Uses a one-hour prompt cache by default (five minutes is a setting)

## May come next

- Vote and choice buttons on the cards, and counting the votes
- A date picker button for finding a date that suits everyone
- Reading photos and locations sent to the group
- Deleting messages on request from the record, the conversation and the summaries, and a retention period for them
- Small in-app pages (LIFF) such as a shared itinerary
- Messages the bot sends without being mentioned (push)

## Not planned

- Booking, paying or any action outside the group: the agent only looks things up and answers
- Access to anything on the host other than its own state folder and the files its configuration names
- Authentication inside the server beyond LINE's signature: exposing the port is the job of the HTTPS entry in front of it (see [SECURITY.md](SECURITY.md))

## Bug reports / feature requests

- Security issues: [SECURITY.md](SECURITY.md)
- Everything else: GitHub Issues (pull requests welcome). Responses are best effort.
