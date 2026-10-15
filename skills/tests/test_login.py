"""Saved connections, login, and the read commands the ask/prep workflows use."""
import json
import os
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIMOIRE_CONFIG_DIR", str(tmp_path / "cfg"))
    for var in ("GRIMOIRE_URL", "GRIMOIRE_API_KEY", "GRIMOIRE_TOKEN", "GRIMOIRE_PROFILE",
                "GRIMOIRE_INSECURE"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "cfg"


def args(api, *argv):
    return api.build_parser().parse_args(list(argv))


GOOD_CHECK = {"url": "http://g", "can_read": {"books": True}, "note": ""}


class TestConfig:
    def test_saved_with_owner_only_permissions(self, api, config_home):
        path = api.save_config({"default_profile": "a", "profiles": {"a": {"api_key": "grim_x"}}})
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert api.load_config()["profiles"]["a"]["api_key"] == "grim_x"

    def test_empty_config(self, api):
        assert api.load_config() == {"default_profile": None, "profiles": {}}

    def test_resolution_order(self, api, monkeypatch):
        api.save_config({"default_profile": "home", "profiles": {
            "home": {"url": "http://home", "api_key": "k-home", "insecure": True},
            "nas": {"url": "http://nas", "api_key": "k-nas"},
        }})
        conn = api.resolve_connection(args(api, "systems"))
        assert conn == {"profile": "home", "url": "http://home", "key": "k-home", "token": None,
                        "insecure": True}
        assert api.resolve_connection(args(api, "--profile", "nas", "systems"))["key"] == "k-nas"
        assert api.resolve_connection(args(api, "systems", "--profile", "nas"))["url"] == "http://nas"
        monkeypatch.setenv("GRIMOIRE_API_KEY", "k-env")
        monkeypatch.setenv("GRIMOIRE_URL", "http://env")
        conn = api.resolve_connection(args(api, "systems"))
        assert (conn["url"], conn["key"]) == ("http://env", "k-env")
        conn = api.resolve_connection(args(api, "--url", "http://flag", "--key", "k-flag", "systems"))
        assert (conn["url"], conn["key"]) == ("http://flag", "k-flag")

    def test_unknown_profile(self, api):
        with pytest.raises(SystemExit):
            api.resolve_connection(args(api, "--profile", "nope", "systems"))

    def test_not_connected_message(self, api, capsys):
        with pytest.raises(SystemExit) as exc:
            api.main(["systems"])
        assert "login" in str(exc.value)


class TestLogin:
    def test_api_key_from_stdin_is_checked_then_saved(self, api, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("grim_secret123\n"))
        monkeypatch.setattr(api, "cmd_check", lambda c, a: dict(GOOD_CHECK, can_read={"books": True}))
        assert api.main(["login", "--url", "grimoire.example.com", "--api-key"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["profile"] == "default" and out["default"] is True
        assert out["key"] == "grim_secr…"
        assert "grim_secret123" not in json.dumps(out)
        saved = api.load_config()["profiles"]["default"]
        assert saved["url"] == "https://grimoire.example.com"
        assert saved["auth"] == "api-key"

    def test_rejected_key_is_not_saved(self, api, monkeypatch):
        monkeypatch.setenv("GRIMOIRE_API_KEY", "grim_bad")
        monkeypatch.setattr(api, "cmd_check", lambda c, a: {"can_read": {"books": "no (401)"}})
        with pytest.raises(SystemExit):
            api.main(["login", "--url", "http://g", "--api-key"])
        assert api.load_config()["profiles"] == {}

    def test_browser_login_receives_the_key(self, api, monkeypatch, capsys):
        opened = []
        monkeypatch.setattr(api.webbrowser, "open", opened.append)
        monkeypatch.setattr(api, "cmd_check", lambda c, a: dict(GOOD_CHECK))

        def browser():
            while not opened:
                time.sleep(0.02)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(opened[0]).query)
            assert q["perms"][0] == api.ACCESS["full"]
            assert q["client"][0].startswith("Grimoire skills on ")
            body = urllib.parse.urlencode({"key": "grim_frombrowser", "state": q["state"][0]})
            urllib.request.urlopen(q["callback"][0], data=body.encode()).read()

        t = threading.Thread(target=browser)
        t.start()
        assert api.main(["login", "--url", "http://g", "--profile", "nas", "--timeout", "10"]) == 0
        t.join()
        assert opened[0].startswith("http://g/connect?")
        saved = api.load_config()
        assert saved["profiles"]["nas"]["api_key"] == "grim_frombrowser"
        assert saved["profiles"]["nas"]["auth"] == "browser"
        assert saved["default_profile"] == "nas"

    def test_wrong_state_is_refused_and_cancel_saves_nothing(self, api, monkeypatch):
        opened = []
        monkeypatch.setattr(api.webbrowser, "open", opened.append)
        statuses = []

        def browser():
            while not opened:
                time.sleep(0.02)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(opened[0]).query)
            cb = q["callback"][0]
            try:
                urllib.request.urlopen(cb, data=b"key=stolen&state=wrong")
            except urllib.error.HTTPError as exc:
                statuses.append(exc.code)
            body = urllib.parse.urlencode({"error": "access_denied", "state": q["state"][0]})
            urllib.request.urlopen(cb, data=body.encode()).read()

        t = threading.Thread(target=browser)
        t.start()
        with pytest.raises(SystemExit) as exc:
            api.browser_login("http://g", "books:read", "test", timeout=10)
        t.join()
        assert statuses == [400]
        assert "cancelled" in str(exc.value)

    def test_browser_timeout(self, api, monkeypatch):
        monkeypatch.setattr(api.webbrowser, "open", lambda url: None)
        with pytest.raises(SystemExit) as exc:
            api.browser_login("http://g", "books:read", "test", timeout=0.3)
        assert "no answer" in str(exc.value)

    def test_no_browser_link_has_no_callback(self, api):
        url = api.connect_url("http://g/", "books:read", "x")
        assert url == "http://g/connect?client=x&perms=books%3Aread"


class TestProfiles:
    def test_profiles_use_logout(self, api, capsys):
        api.save_config({"default_profile": "a", "profiles": {
            "a": {"url": "http://a", "api_key": "grim_aaaaaaaaa"},
            "b": {"url": "http://b", "api_key": "grim_bbbbbbbbb"},
        }})
        listed = api.cmd_profiles(args(api, "profiles"))
        assert [p["profile"] for p in listed] == ["a", "b"]
        assert all("…" in p["key"] for p in listed)
        assert api.cmd_use(args(api, "use", "b")) == {"default_profile": "b"}
        out = api.cmd_logout(args(api, "logout"))
        assert out["removed"] == "b" and out["default_profile"] == "a"
        assert "revoke" in out["note"]
        with pytest.raises(SystemExit):
            api.cmd_use(args(api, "use", "zzz"))

    def test_notes(self, api, config_home):
        api.save_config({"default_profile": "a", "profiles": {"a": {"url": "u", "api_key": "k"}}})
        empty = api.cmd_notes(args(api, "notes"))
        assert empty["exists"] is False and empty["path"].endswith("libraries/a.md")
        notes = config_home / "libraries" / "a.md"
        notes.parent.mkdir(parents=True)
        notes.write_text("## Conventions\n- lowercase core\n")
        assert "lowercase core" in api.cmd_notes(args(api, "notes"))["content"]


class FakeReads:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, **params):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/text"):
            return {"text": "page " + endpoint.split("/")[-2]}
        return {"ok": True}


class TestReadCommands:
    def test_search_and_pages(self, api):
        c = FakeReads()
        api.run(args(api, "search", "grapple", "--system", "s1"), c)
        assert c.calls[-1] == ("/api/search", {"q": "grapple", "system_id": "s1", "book_id": None,
                                               "limit": 20})
        pages = api.run(args(api, "pages", "b1", "3", "40"), c)
        assert [p["page"] for p in pages] == list(range(3, 13))  # capped at ten pages
        assert pages[0]["text"] == "page 3"

    def test_campaign_commands(self, api):
        c = FakeReads()
        api.run(args(api, "campaigns"), c)
        api.run(args(api, "campaign", "c1"), c)
        api.run(args(api, "wiki", "c1"), c)
        api.run(args(api, "wiki", "c1", "p1"), c)
        api.run(args(api, "wiki-search", "c1", "baron"), c)
        assert [e for e, _ in c.calls] == [
            "/api/campaigns", "/api/campaigns/c1", "/api/campaigns/c1/wiki",
            "/api/campaigns/c1/wiki/p1", "/api/campaigns/c1/wiki/search",
        ]
        assert c.calls[-1][1] == {"q": "baron"}

    def test_insecure_client_skips_verification(self, api):
        import ssl

        assert api.Client("https://g", "k", insecure=True).ssl.verify_mode == ssl.CERT_NONE
        assert api.Client("https://g", "k").ssl is None
