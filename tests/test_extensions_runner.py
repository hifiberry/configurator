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


def test_uninstall_builds_a_remove_argv():
    executor = FakeExecutor()
    runner = _runner(
        packages=[_extension_info(installed="1.0.2")],
        executor=executor,
    )
    job = runner.uninstall("hifiberry-tidal-connect")
    argv = executor.calls[0]
    assert "remove" in argv
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
