# Importing an old chat history

A group's record only starts when the bot joins. To let the bot find things said before that
("what did we decide about the hotel last year?"), you can put an old chat history into the
record.

1. In LINE, open the group's chat menu and choose **Send chat history** (トーク履歴を送信).
   It makes a `.txt` file; save it on the machine that runs the agent
2. Stop the agent. The command replaces the record file whole, so a message written at the same
   moment would be lost
3. Run

   ```
   line-group-agent import-history --config <path to config.json> --group <groupId> <history.txt>
   ```

   (`<groupId>` is the id the agent logs for the group, the same one as in
   `allowed_group_ids`.) With the repository checked out, `uv run line-group-agent import-history …`
   works the same way
4. Start the agent again

The command prints what it did:

```
added 1240 message(s); 3 already in the record; 18 notice line(s) skipped; 2 line(s) not understood
```

## What it does

- Reads the file: a date line (`2026/11/17(火)`, `2026-11-17`, `Tue, 11/17/2026` …), then a line per
  message with the time, the sender's name and the text, separated by tabs. A text of several
  lines (wrapped in double quotes in the file) is one message
- Adds each message to `groups/<groupId>/messages.jsonl` in time order, in front of newer
  messages, with `"imported": true`. The names are the ones in the file; there is no user id
- Leaves out a message the record already holds (the same minute, name and text), so running the
  command again, or importing a history that overlaps the record, adds nothing twice
- Photos, stickers and the like are in the file only as text such as `[写真]`, and are recorded as
  that text; the photos themselves are not imported

## Things to know

- **Imported messages are not deleted by age.** They are old by nature, so `retention_days` does
  not apply to them. They are deleted like any message when a member asks the bot to delete
  something that is theirs and it matches, or by removing them from the file by hand
- **The bot's earlier messages are ordinary messages here**, under the name the file has for
  them, not the bot's own replies
- Notice lines (someone joined, a message was taken back) are skipped and counted. A line of a
  shape the command does not know is skipped and counted as "not understood", and the rest of the
  file is still read. If everything is "not understood", the file is in a form this version does
  not read: please open an issue with a few lines of it, with the names and texts changed
- The file is read as UTF-8 (a byte order mark is fine); a character that cannot be read is
  replaced and the import goes on
