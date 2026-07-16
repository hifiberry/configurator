import json

from configurator.extensions.github import GitHubCatalog


class FakeSources:
    def __init__(self, repos):
        self._repos = repos

    def list_sources(self):
        return [{"id": r.replace("/", "-"), "repo": r} for r in self._repos]


def _release(deb="hifiberry-tidal-connect_1.0.0_arm64.deb", extra_assets=None,
             meta=None):
    meta_obj = {
        "package": "hifiberry-tidal-connect",
        "name": "Tidal Connect",
        "category": "player",
        "version": "1.0.0",
        "needs_reboot": "maybe",
        "icon": "tidal",
        "description": "Tidal Connect endpoint\n Stream from the app.",
        "deb": deb,
        "sha256": "abc123",
    }
    if meta is not None:
        meta_obj.update(meta)
    assets = [
        {"name": "extension.json",
         "browser_download_url": "https://gh/assets/extension.json"},
        {"name": deb, "browser_download_url": f"https://gh/assets/{deb}"},
    ]
    assets.extend(extra_assets or [])
    return {"assets": assets}, meta_obj


class FakeFetcher:
    """Serves a canned releases-latest json and extension.json bytes; counts hits."""

    def __init__(self, release_json, meta_obj, fail_repos=()):
        self.release_json = release_json
        self.meta_bytes = json.dumps(meta_obj).encode()
        self.fail_repos = fail_repos
        self.json_calls = 0
        self.bytes_calls = 0

    def get_json(self, url):
        self.json_calls += 1
        for repo in self.fail_repos:
            if repo in url:
                raise OSError("404")
        return self.release_json

    def get_bytes(self, url):
        self.bytes_calls += 1
        return self.meta_bytes


def _catalog(repos=("pulpier/tidal-connect-hifiberry",), release=None,
             installed=None, fail_repos=(), clock=lambda: 1000.0, cache_ttl=60):
    rel, meta = release or _release()
    fetcher = FakeFetcher(rel, meta, fail_repos=fail_repos)
    catalog = GitHubCatalog(
        source_manager=FakeSources(list(repos)),
        fetcher=fetcher,
        installed_version=installed or (lambda pkg: None),
        clock=clock,
        cache_ttl=cache_ttl,
    )
    return catalog, fetcher


def test_builds_extension_from_release():
    catalog, _ = _catalog()
    exts = catalog.list_extensions()
    assert len(exts) == 1
    e = exts[0]
    assert e.package == "hifiberry-tidal-connect"
    assert e.name == "Tidal Connect"
    assert e.category == "player"
    assert e.version == "1.0.0"
    assert e.needs_reboot == "maybe"
    assert e.source == "github:pulpier/tidal-connect-hifiberry"
    assert e.download_url == "https://gh/assets/hifiberry-tidal-connect_1.0.0_arm64.deb"
    assert e.sha256 == "abc123"
    assert e.state == "available"


def test_installed_version_makes_state_installed():
    catalog, _ = _catalog(installed=lambda pkg: "1.0.0")
    assert catalog.list_extensions()[0].state == "installed"


def test_older_installed_makes_state_upgradable():
    catalog, _ = _catalog(installed=lambda pkg: "0.9.0")
    assert catalog.list_extensions()[0].state == "upgradable"


def test_bare_icon_name_does_not_become_a_broken_url():
    catalog, _ = _catalog()
    assert catalog.list_extensions()[0].icon_url is None


def test_full_icon_url_is_kept():
    rel = _release(meta={"icon": "https://example.com/tidal.svg"})
    catalog, _ = _catalog(release=rel)
    assert catalog.list_extensions()[0].icon_url == "https://example.com/tidal.svg"


def test_missing_extension_json_asset_skips_source():
    rel_json, meta = _release()
    rel_json = {"assets": [a for a in rel_json["assets"] if a["name"] != "extension.json"]}
    catalog = GitHubCatalog(
        source_manager=FakeSources(["a/b"]),
        fetcher=FakeFetcher(rel_json, meta),
        installed_version=lambda pkg: None,
    )
    assert catalog.list_extensions() == []


def test_deb_asset_not_in_release_skips_source():
    # extension.json names a deb that is not among the release assets
    rel = _release(meta={"deb": "not-present.deb"})
    catalog, _ = _catalog(release=rel)
    assert catalog.list_extensions() == []


def test_invalid_package_name_skips_source():
    rel = _release(meta={"package": "Bad Name"})
    catalog, _ = _catalog(release=rel)
    assert catalog.list_extensions() == []


def test_a_failing_source_does_not_break_others():
    catalog, _ = _catalog(
        repos=("bad/repo", "pulpier/tidal-connect-hifiberry"),
        fail_repos=("bad/repo",),
    )
    pkgs = [e.package for e in catalog.list_extensions()]
    assert pkgs == ["hifiberry-tidal-connect"]


def test_release_json_is_cached_within_ttl():
    catalog, fetcher = _catalog()
    catalog.list_extensions()
    first = fetcher.json_calls
    catalog.list_extensions()
    assert fetcher.json_calls == first  # no second releases/latest fetch


def test_get_extension_returns_the_entry_with_download_info():
    catalog, _ = _catalog()
    e = catalog.get_extension("hifiberry-tidal-connect")
    assert e is not None
    assert e.download_url.endswith(".deb")
    assert catalog.get_extension("nope") is None
