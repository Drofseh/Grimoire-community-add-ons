# Setup: connect to a Grimoire library

Goal: a saved, working connection, plus a notes file describing the library -
in one step for the user wherever possible.

## 1. Find the address

Ask for their Grimoire address if they have not given it - the URL they open in
the browser, e.g. `https://grimoire.example.com` or `http://nas.local:9481`. A
Grimoire behind a sub-path (`https://example.com/grimoire`) works with that full
URL.

## 2. Sign in

**Browser sign-in (default).** Run this yourself - it opens the user's browser
and waits up to five minutes, so give the command a long timeout (or run it in
the background and wait for it):

```bash
G login --url <address> [--profile <name>]
```

Tell the user what to expect: a Grimoire page titled *Connect Grimoire skills
to Grimoire* that lists the access requested; they sign in the way they normally
do (password or single sign-on), check the list, and press **Allow**. The page
sends the new key straight back to the waiting command on this computer - the
key never appears in the chat. The page shows anything their account cannot
grant (non-admins cannot get the file manager or rescans, so organising needs an
admin; enrich, ask and prep work for GMs).

Other ways in, when that does not fit:

| Situation | Command |
|---|---|
| The browser is on a different machine (SSH, container, remote desktop) | `G login --url <address> --no-browser` - prints a link; they open it anywhere, press Allow, and paste the key into the prompt **in their own terminal** |
| They already have an API key | Ask them to run `G login --url <address> --api-key` in their own terminal (it prompts with hidden input), or to start you with `GRIMOIRE_API_KEY` set so you can run it |
| Read-only use (ask, prep, identify against the library) | add `--access read` |
| Self-signed TLS certificate | add `--insecure` (it is remembered for that library); for a private CA, set `SSL_CERT_FILE` instead |
| A second library | `--profile <name>`; `G use <name>` switches the default |

Give the user the exact command with `<skill-dir>` expanded to the real path when
they need to run it themselves.

If you are running somewhere that cannot open a browser or reach their machine
(a cloud sandbox), use `--no-browser`.

## 3. When it fails

| Symptom | Cause and fix |
|---|---|
| "got a web page instead of JSON" | A login proxy (Authentik, Authelia, oauth2-proxy) sits in front of Grimoire. Use the internal address that skips it, or have the proxy let `/api/` through for requests carrying `X-API-Key` |
| `403 API keys are disabled on this server` | The server runs with `API_KEYS_ENABLED=false`; the admin must turn keys on |
| The connect page says keys aren't available for the account | An admin needs to tick **API keys** for the user in Settings → Users |
| The browser shows Grimoire's library instead of the connect page | The server is older than the connect page - use `--api-key` with a key made in Settings → Account → Security → API Keys |
| Certificate errors | `--insecure` for self-signed, `SSL_CERT_FILE=/path/ca.pem` for a private CA |
| No answer from the browser | They closed the tab or took longer than 5 minutes - run `login` again |

## 4. Learn the library and write its notes

Once connected, look at the library and write what you find into the notes
file (`G notes` prints its path; create it if missing):

```bash
G systems
G tree books --depth 2
G lookups
```

Record conventions, not inventory:

```markdown
# <profile> - <address>

## Conventions
- Systems with several editions use parent-system containers (Ars Magica/5th Edition)
- Category folders: lowercase `core`, `adventures`, `supplements`
- Non-English books in a `[DE]` / `[FR]` subfolder of their category
- Third-party books in `supplements/3rd Party/<Publisher>/`

## Preferences
- (what the user tells you - ask if there is anything they always want)

## History
- 2026-10-14: connected
```

Ask the user if they have preferences to add (naming, where community content
goes, what to tag). Show them the notes when done.

## 5. Finish

Confirm with `G check` and tell the user: which library is connected and as
which profile, what the key can do, and that they can manage or revoke it under
Settings → Account → Security → API Keys. `G logout` forgets a saved library (the
key keeps working until revoked in Grimoire).
