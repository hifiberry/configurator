import pytest

from configurator.extensions.catalog import ExtensionCatalog, PackageInfo
from configurator.extensions.jobs import (
    JobRegistry,
    PHASE_DONE,
    PHASE_FAILED,
)
from configurator.extensions.runner import (
    ExtensionRunner,
    InvalidPackageName,
    NotAnExtension,
)


def _extension_info(name="hifiberry-tidal-connect", installed=None):
    return PackageInfo(
        name=name,
        record={
            "Package": name,
            "Description": "Tidal Connect endpoint",
            "XB-Hifiberry-Extension": "yes",
            "XB-Extension-Name": "Tidal Connect",
            "XB-Extension-Category": "player",
        },
        candidate_version="1.0.2",
        installed_version=installed,
    )


def _plain_info(name="openssh-server"):
    return PackageInfo(name=name, record={"Package": name}, candidate_version="1.0")


class FakeExecutor:
    """Stands in for apt. Records argv, replays canned output, returns rc."""

    def __init__(self, returncode=0, lines=()):
        self.returncode = returncode
        self.lines = list(lines)
        self.calls = []

    def __call__(self, argv, job):
        self.calls.append(argv)
        for line in self.lines:
            job.append_log(line)
        return self.returncode


def _runner(packages=None, executor=None, refresher=None):
    packages = packages if packages is not None else [_extension_info()]
    catalog = ExtensionCatalog(package_source=lambda: packages)
    return ExtensionRunner(
        catalog=catalog,
        jobs=JobRegistry(),
        executor=executor or FakeExecutor(),
        refresher=refresher or (lambda: None),
        # Run inline so tests are deterministic without sleeping. staticmethod
        # matters: a plain function here would bind as a method and be handed
        # `self` when .start() is called.
        thread_factory=lambda target: type("T", (), {"start": staticmethod(target)})(),
    )


def test_install_rejects_an_unmarked_package():
    runner = _runner(packages=[_plain_info()])
    with pytest.raises(NotAnExtension):
        runner.install("openssh-server")


def test_install_rejects_an_unknown_package():
    with pytest.raises(NotAnExtension):
        _runner().install("does-not-exist")


@pytest.mark.parametrize("bad", [
    "openssh-server; rm -rf /",
    "../../etc/passwd",
    "Foo",
    "-o",
    "",
    "pkg name",
])
def test_install_rejects_injection_shaped_names(bad):
    with pytest.raises((InvalidPackageName, NotAnExtension)):
        _runner().install(bad)


def test_install_builds_a_noninteractive_apt_argv():
    executor = FakeExecutor()
    _runner(executor=executor).install("hifiberry-tidal-connect")
    argv = executor.calls[0]
    assert argv[0].endswith("apt-get")
    assert "-y" in argv
    assert "install" in argv
    assert argv[-1] == "hifiberry-tidal-connect"
    # The package name must never be interpretable as an option.
    assert argv[argv.index("install") - 1] != "-o"


def test_successful_install_ends_done():
    job = _runner().install("hifiberry-tidal-connect")
    assert job.phase == PHASE_DONE
    assert job.exit_code == 0


def test_failed_install_ends_failed_with_exit_code():
    job = _runner(executor=FakeExecutor(returncode=100)).install("hifiberry-tidal-connect")
    assert job.phase == PHASE_FAILED
    assert job.exit_code == 100


def test_failed_install_keeps_the_log_for_diagnosis():
    executor = FakeExecutor(returncode=100, lines=["E: Unable to locate package"])
    job = _runner(executor=executor).install("hifiberry-tidal-connect")
    assert "E: Unable to locate package" in job.to_dict()["log"]


def test_refresher_runs_after_a_successful_install():
    called = []
    _runner(refresher=lambda: called.append(True)).install("hifiberry-tidal-connect")
    assert called == [True]


def test_refresher_does_not_run_after_a_failed_install():
    called = []
    _runner(
        executor=FakeExecutor(returncode=100),
        refresher=lambda: called.append(True),
    ).install("hifiberry-tidal-connect")
    assert called == []


def test_uninstall_rejects_an_unmarked_package():
    runner = _runner(packages=[_plain_info()])
    with pytest.raises(NotAnExtension):
        runner.uninstall("openssh-server")


def test_uninstall_builds_a_purge_argv():
    executor = FakeExecutor()
    runner = _runner(
        packages=[_extension_info(installed="1.0.2")],
        executor=executor,
    )
    job = runner.uninstall("hifiberry-tidal-connect")
    argv = executor.calls[0]
    # purge (not remove) so conffile registrations and postrm-purge cleanup run
    assert "purge" in argv
    assert "remove" not in argv
    assert argv[-1] == "hifiberry-tidal-connect"
    assert job.phase == PHASE_DONE


def test_refresher_runs_after_a_successful_uninstall():
    called = []
    _runner(
        packages=[_extension_info(installed="1.0.2")],
        refresher=lambda: called.append(True),
    ).uninstall("hifiberry-tidal-connect")
    assert called == [True]


def test_refresh_builds_an_update_argv_and_needs_no_package():
    executor = FakeExecutor()
    job = _runner(executor=executor).refresh()
    assert "update" in executor.calls[0]
    assert job.action == "refresh"
    assert job.phase == PHASE_DONE


# --- AptExecutor: systemd-run wrapping + status/log routing ------------------
# The executor is normally the injected seam (tests use FakeExecutor), but the
# systemd-run wrapping and APT::Status-Fd=1 line routing are real logic worth
# locking without actually shelling out to apt.

class _FakeStdout:
    def __init__(self, lines):
        self._it = iter(lines)

    def __iter__(self):
        return self._it

    def close(self):
        pass


class _FakeProc:
    def __init__(self, lines, returncode):
        self.stdout = _FakeStdout(lines)
        self._rc = returncode

    def wait(self):
        return self._rc


def test_apt_executor_wraps_apt_in_systemd_run(monkeypatch):
    from configurator.extensions import runner as runner_mod
    from configurator.extensions.jobs import JobRegistry as _JR

    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc([], 0)

    monkeypatch.setattr(runner_mod.subprocess, "Popen", fake_popen)
    job = _JR().create("hifiberry-tidal-connect", "install")
    rc = runner_mod.AptExecutor()(
        ["/usr/bin/apt-get", "-y", "install", "hifiberry-tidal-connect"], job
    )
    cmd = captured["cmd"]
    assert rc == 0
    assert cmd[0].endswith("systemd-run")
    for flag in ("--pipe", "--wait", "--collect", "--quiet"):
        assert flag in cmd
    assert "--setenv=DEBIAN_FRONTEND=noninteractive" in cmd
    # the real apt argv is passed through, and status is routed to stdout
    assert "/usr/bin/apt-get" in cmd and "install" in cmd
    assert cmd[-2:] == ["-o", "APT::Status-Fd=1"]


def test_apt_executor_routes_status_lines_and_logs_the_rest(monkeypatch):
    from configurator.extensions import runner as runner_mod
    from configurator.extensions.jobs import JobRegistry as _JR, PHASE_INSTALLING

    lines = [
        "Reading package lists...\n",
        "pmstatus:hifiberry-tidal-connect:50.0:Unpacking\n",
        "Setting up hifiberry-tidal-connect...\n",
    ]
    monkeypatch.setattr(runner_mod.subprocess, "Popen",
                        lambda cmd, **kw: _FakeProc(lines, 0))
    job = _JR().create("hifiberry-tidal-connect", "install")
    runner_mod.AptExecutor()(["/usr/bin/apt-get", "-y", "install", "x"], job)
    data = job.to_dict()
    # a status line updated phase/percent
    assert job.phase == PHASE_INSTALLING
    assert job.percent == 50.0
    # plain lines were logged; the status message was logged too
    assert "Reading package lists..." in data["log"]
    assert "Unpacking" in data["log"]


def test_apt_executor_returns_127_when_systemd_run_missing(monkeypatch):
    from configurator.extensions import runner as runner_mod
    from configurator.extensions.jobs import JobRegistry as _JR

    def boom(cmd, **kw):
        raise OSError("systemd-run not found")

    monkeypatch.setattr(runner_mod.subprocess, "Popen", boom)
    job = _JR().create("x", "install")
    rc = runner_mod.AptExecutor()(["/usr/bin/apt-get", "-y", "install", "x"], job)
    assert rc == 127


# --- GitHub install path (download -> verify sha256 + marker -> apt install file)
import hashlib as _hashlib


def _github_runner(executor=None, downloader=None, marker_ok=True, refresher=None):
    from configurator.extensions import runner as runner_mod
    from configurator.extensions.catalog import ExtensionCatalog
    from configurator.extensions.jobs import JobRegistry as _JR
    catalog = ExtensionCatalog(package_source=lambda: [])  # not used by github path
    return runner_mod.ExtensionRunner(
        catalog=catalog,
        jobs=_JR(),
        executor=executor or FakeExecutor(),
        downloader=downloader or (lambda url: b"DEBDATA"),
        deb_marker_check=lambda path: marker_ok,
        refresher=refresher or (lambda: None),
        thread_factory=lambda target: type("T", (), {"start": staticmethod(target)})(),
    )


def _sha(data):
    return _hashlib.sha256(data).hexdigest()


def test_github_install_verifies_sha_then_installs_the_file():
    executor = FakeExecutor()
    runner = _github_runner(executor=executor, downloader=lambda url: b"DEBDATA")
    job = runner.install_github("hifiberry-tidal-connect",
                                "https://gh/x.deb", _sha(b"DEBDATA"))
    assert job.phase == PHASE_DONE
    argv = executor.calls[0]
    assert "install" in argv
    assert argv[-1].endswith(".deb")
    assert "/" in argv[-1]  # a path, so apt installs the local file


def test_github_install_refuses_on_sha_mismatch_before_apt():
    executor = FakeExecutor()
    runner = _github_runner(executor=executor, downloader=lambda url: b"DEBDATA")
    job = runner.install_github("hifiberry-tidal-connect", "https://gh/x.deb",
                                "0" * 64)
    assert job.phase == PHASE_FAILED
    assert "checksum" in job.error.lower()
    assert executor.calls == []  # apt never ran


def test_github_install_refuses_unmarked_deb_before_apt():
    executor = FakeExecutor()
    runner = _github_runner(executor=executor, marker_ok=False,
                            downloader=lambda url: b"DEBDATA")
    job = runner.install_github("hifiberry-tidal-connect", "https://gh/x.deb",
                                _sha(b"DEBDATA"))
    assert job.phase == PHASE_FAILED
    assert "not a hifiberry extension" in job.error.lower()
    assert executor.calls == []


def test_github_install_rejects_bad_package_name():
    import pytest as _pytest
    runner = _github_runner()
    with _pytest.raises(InvalidPackageName):
        runner.install_github("Bad Name", "https://gh/x.deb", "abc")


def test_github_install_download_failure_is_reported():
    def boom(url):
        raise OSError("network down")
    runner = _github_runner(downloader=boom)
    job = runner.install_github("hifiberry-tidal-connect", "https://gh/x.deb", "abc")
    assert job.phase == PHASE_FAILED
    assert "download failed" in job.error.lower()
