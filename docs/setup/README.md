# Setup

## 1. Install

```bash
git clone https://github.com/Synforger/line-group-agent.git
cd line-group-agent
task setup          # or: uv sync --python 3.12
```

`task doctor` reports missing tools.

## 2. Create the LINE channel

In the [LINE Developers Console](https://developers.line.biz/console/):

1. Create a provider and a **Messaging API** channel (this creates the LINE
   Official Account).
2. On **Basic settings**, copy the **Channel secret**.
3. On **Messaging API**, issue a **Channel access token (long-lived)**.
4. In the LINE Official Account Manager, allow the account to join group chats
   and turn off the automatic reply and greeting messages.

## 3. Put the secrets in files

One value per file, readable only by you:

```bash
mkdir -p /path/to/secrets && chmod 700 /path/to/secrets
printf '%s' '<claude api key>'            > /path/to/secrets/anthropic-api-key
printf '%s' '<channel secret>'            > /path/to/secrets/line-channel-secret
printf '%s' '<channel access token>'      > /path/to/secrets/line-channel-access-token
chmod 600 /path/to/secrets/*
```

The agent reads them once at start and never logs them. Keep them outside the
repository.

## 4. Write the configuration and the persona

Copy [`configs/config.example.json`](../../configs/config.example.json) outside
the repository and edit it. Every setting is described in
[the configuration reference](../reference/config.md). The persona file is plain text
that becomes the start of the model's system text: who the bot is and how it
speaks. The agent adds its own fixed rules after it (group messages are data,
only `<reply>` is sent, keep it short).

## 5. Start it and connect LINE

```bash
uv run line-group-agent --config /path/to/config.json
```

Make `https://<your-host>/line/webhook` reach `http://127.0.0.1:8790/line/webhook`
(a reverse proxy or a tunnel), set it as the **Webhook URL** on the channel's
**Messaging API** tab, press **Verify** and turn on **Use webhook**.

Invite the account to the group. The agent logs the group's id once:

```
join: joined a group that is not allowed: group_id=C0123456789abcdef0123456789abcdef
```

Add that id to `allowed_group_ids` and restart. Mention the account in the group
to ask it something.

## 6. Run it as a service

Install into an environment of its own and call the executable directly. The
agent needs no environment variables and no particular working directory.

macOS (launchd), `~/Library/LaunchAgents/com.example.line-group-agent.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.example.line-group-agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/line-group-agent/.venv/bin/line-group-agent</string>
    <string>--config</string>
    <string>/path/to/config.json</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/path/to/logs/line-group-agent.log</string>
</dict>
</plist>
```

Linux (systemd), a unit's service section:

```ini
[Service]
ExecStart=/path/to/line-group-agent/.venv/bin/line-group-agent --config /path/to/config.json
Restart=on-failure
```

Restart the service after changing the configuration or the persona.
