import os

import pytest

from configurator.extensions.github import (
    GitHubSourceManager,
    GitHubSourceNotFound,
    InvalidGitHubSource,
)


def _manager(tmp_path):
    return GitHubSourceManager(sources_dir=str(tmp_path / "extension-sources.d"))


def test_add_source_writes_a_file_and_returns_id(tmp_path):
    manager = _manager(tmp_path)
    result = manager.add_source("pulpier/tidal-connect-hifiberry")
    assert result == {"id": "pulpier-tidal-connect-hifiberry",
                      "repo": "pulpier/tidal-connect-hifiberry"}
    path = tmp_path / "extension-sources.d" / "pulpier-tidal-connect-hifiberry.json"
    assert path.exists()
    assert oct(os.stat(path).st_mode)[-3:] == "644"


def test_list_sources_returns_added_sources(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("pulpier/tidal-connect-hifiberry")
    sources = manager.list_sources()
    assert sources == [{"id": "pulpier-tidal-connect-hifiberry",
                        "repo": "pulpier/tidal-connect-hifiberry"}]


def test_list_sources_empty_when_dir_absent(tmp_path):
    assert _manager(tmp_path).list_sources() == []


def test_list_sources_skips_unreadable(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("a/b")
    (tmp_path / "extension-sources.d" / "junk.json").write_text("not json")
    assert [s["repo"] for s in manager.list_sources()] == ["a/b"]


@pytest.mark.parametrize("bad", ["../etc/evil", "noslash", "a b/c", "a/b/c", "", "/leading"])
def test_bad_repo_shapes_are_refused(tmp_path, bad):
    with pytest.raises(InvalidGitHubSource):
        _manager(tmp_path).add_source(bad)


def test_bad_repo_writes_nothing(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(InvalidGitHubSource):
        manager.add_source("../evil")
    assert not (tmp_path / "extension-sources.d").exists() or \
        os.listdir(tmp_path / "extension-sources.d") == []


def test_remove_source_deletes_file(tmp_path):
    manager = _manager(tmp_path)
    manager.add_source("a/b")
    manager.remove_source("a-b")
    assert manager.list_sources() == []


def test_remove_unknown_raises_not_found(tmp_path):
    with pytest.raises(GitHubSourceNotFound):
        _manager(tmp_path).remove_source("nope")


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "a/b", ""])
def test_remove_refuses_unsafe_id(tmp_path, bad_id):
    with pytest.raises(InvalidGitHubSource):
        _manager(tmp_path).remove_source(bad_id)
