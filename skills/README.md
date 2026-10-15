# Assistant skills

Skills teach an AI assistant - Claude Code, or any client that reads `SKILL.md`
skills - how to work with Grimoire. Like note templates, they are **not installed
into a server**: each user installs them into their own assistant, and they talk
to Grimoire through its API with that user's own access.

| Skill | What it does |
| --- | --- |
| [`grimoire`](grimoire/SKILL.md) | `/grimoire` - connect to a library (browser sign-in or API key), organise a pile of unsorted PDFs into it, find broken books, identify and file books, fill in metadata, answer rules questions from your books with page citations, and prep a campaign's next session |

## Installing

```bash
npx skills add grimoire-codex/community-add-ons
```

or copy the folder into Claude Code's skills directory:

```bash
git clone --depth 1 https://github.com/grimoire-codex/community-add-ons.git /tmp/grimoire-add-ons
cp -r /tmp/grimoire-add-ons/skills/grimoire ~/.claude/skills/
```

Then run `/grimoire setup` in Claude Code. The full user guide is
[The /grimoire skill](https://github.com/hunter-read/grimoire/blob/main/docs/library-skills.md)
in the Grimoire docs.

## What a skill can do

A skill is instructions plus, optionally, scripts that run **on the user's own
computer** when the assistant decides to - never on the Grimoire server. Whatever
a skill does in Grimoire goes through an API key, so it can do no more than the
key's owner could in the app, and the key's permissions are shown to the user
when they create it. Read a skill's scripts before installing it, as you would
any code you run.

## Adding a skill

1. Put it in its own folder, `skills/<name>/`, with a `SKILL.md` whose
   frontmatter `name` is the folder name and whose `description` (at most 1024
   characters) says what it does and when to use it.
2. Keep the user in control: nothing changes in their library without their
   approval, and API keys never go through the chat.
3. Scripts use the Python standard library (plus PyMuPDF if they read PDFs) and
   run on Python 3.9+. Put tests in `skills/tests/`.
4. `python3 scripts/build_index.py --check` validates every skill's frontmatter
   and checks its scripts compile; CI also runs `python3 -m pytest skills/tests`.

Per-user behaviour - a library's naming conventions, what someone always wants
tagged - belongs in the notes file the `grimoire` skill keeps for each library
(`~/.config/grimoire/libraries/<profile>.md`), not in a fork of the skill.
