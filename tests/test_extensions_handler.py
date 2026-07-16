import json

import pytest
flask = pytest.importorskip("flask", reason="Flask is absent in the build chroot")

from flask import Flask

from configurator.extensions.catalog import ExtensionCatalog, PackageInfo
from configurator.extensions.jobs import ExtensionBusy, JobRegistry, PHASE_DONE
from configurator.extensions.runner import InvalidPackageName, NotAnExtension
from configurator.extensions.sources import InvalidSource
from configurator.handlers.extensions_handler import ExtensionsHandler


def _extension_info(name="hifiberry-tidal-connect"):
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
        installed_version=None,
    )


class FakeRunner:
    def __init__(self, jobs, raises=None):
        self.jobs = jobs
        self.raises = raises
        self.calls = []

    def _maybe_raise(self):
        if self.raises:
            raise self.raises

    def install(self, package):
        self.calls.append(("install", package))
        self._maybe_raise()
        return self.jobs.create(package, "install")

    def uninstall(self, package):
        self.calls.append(("uninstall", package))
        self._maybe_raise()
        return self.jobs.create(package, "uninstall")

    def refresh(self):
        self.calls.append(("refresh", None))
        self._maybe_raise()
        return self.jobs.create(None, "refresh")


class FakeSources:
    def __init__(self, raises=None):
        self.raises = raises
        self.sources = []
        self.removed = []

    def list_sources(self):
        return self.sources

    def add_source(self, source_id, uri, suite, components, key_armored):
        if self.raises:
            raise self.raises
        source = {"id": source_id, "uri": uri, "suite": suite,
                  "components": components, "keyring": "/k.gpg"}
        self.sources.append(source)
        return source

    def remove_source(self, source_id):
        if self.raises:
            raise self.raises
        self.removed.append(source_id)


def _handler(packages=None, runner=None, sources=None, jobs=None,
             reboot_flag_path="/nonexistent"):
    packages = packages if packages is not None else [_extension_info()]
    jobs = jobs or JobRegistry()
    catalog = ExtensionCatalog(package_source=lambda: packages)
    return ExtensionsHandler(
        catalog=catalog,
        jobs=jobs,
        runner=runner if runner is not None else FakeRunner(jobs),
        sources=sources if sources is not None else FakeSources(),
        reboot_flag_path=reboot_flag_path,
    )


def _call(fn, *args, **kwargs):
    """Invoke a handler inside a request context and return (status, payload)."""
    app = Flask(__name__)
    with app.test_request_context(**kwargs):
        result = fn(*args)
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, 200
    return status, json.loads(response.get_data(as_text=True))


def test_list_extensions_returns_the_catalog():
    status, payload = _call(_handler().handle_list_extensions)
    assert status == 200
    assert payload["status"] == "success"
    assert payload["data"]["extensions"][0]["package"] == "hifiberry-tidal-connect"


def test_get_extension_returns_detail():
    status, payload = _call(_handler().handle_get_extension, "hifiberry-tidal-connect")
    assert status == 200
    assert payload["data"]["name"] == "Tidal Connect"


def test_get_unknown_extension_is_404():
    status, payload = _call(_handler().handle_get_extension, "openssh-server")
    assert status == 404
    assert payload["status"] == "error"


def test_install_returns_a_job_id():
    status, payload = _call(_handler().handle_install, "hifiberry-tidal-connect")
    assert status == 202
    assert payload["data"]["job"]["action"] == "install"
    assert payload["data"]["job"]["id"]


def test_install_of_an_unmarked_package_is_403():
    jobs = JobRegistry()
    handler = _handler(runner=FakeRunner(jobs, raises=NotAnExtension("nope")), jobs=jobs)
    status, payload = _call(handler.handle_install, "openssh-server")
    assert status == 403
    assert payload["status"] == "error"


def test_install_with_an_invalid_name_is_400():
    jobs = JobRegistry()
    handler = _handler(runner=FakeRunner(jobs, raises=InvalidPackageName("bad")), jobs=jobs)
    status, _ = _call(handler.handle_install, "Bad Name")
    assert status == 400


def test_install_while_busy_is_409():
    jobs = JobRegistry()
    handler = _handler(runner=FakeRunner(jobs, raises=ExtensionBusy("busy")), jobs=jobs)
    status, payload = _call(handler.handle_install, "hifiberry-tidal-connect")
    assert status == 409
    assert "busy" in payload["message"].lower() or payload["status"] == "error"


def test_uninstall_returns_a_job():
    status, payload = _call(_handler().handle_uninstall, "hifiberry-tidal-connect")
    assert status == 202
    assert payload["data"]["job"]["action"] == "uninstall"


def test_refresh_returns_a_job():
    status, payload = _call(_handler().handle_refresh)
    assert status == 202
    assert payload["data"]["job"]["action"] == "refresh"


def test_get_job_returns_job_state():
    jobs = JobRegistry()
    handler = _handler(jobs=jobs)
    _, created = _call(handler.handle_install, "hifiberry-tidal-connect")
    job_id = created["data"]["job"]["id"]

    status, payload = _call(handler.handle_get_job, job_id)
    assert status == 200
    assert payload["data"]["job"]["id"] == job_id


def test_get_unknown_job_is_404():
    status, _ = _call(_handler().handle_get_job, "nope")
    assert status == 404


def test_finished_job_reports_reboot_required(tmp_path):
    flag = tmp_path / "reboot-required"
    flag.write_text("")
    jobs = JobRegistry()
    handler = _handler(jobs=jobs, reboot_flag_path=str(flag))
    _, created = _call(handler.handle_install, "hifiberry-tidal-connect")
    job_id = created["data"]["job"]["id"]
    jobs.get(job_id).finish(PHASE_DONE)

    _, payload = _call(handler.handle_get_job, job_id)
    assert payload["data"]["reboot_required"] is True


def test_unfinished_job_does_not_report_reboot_required(tmp_path):
    flag = tmp_path / "reboot-required"
    flag.write_text("")
    handler = _handler(reboot_flag_path=str(flag))
    _, created = _call(handler.handle_install, "hifiberry-tidal-connect")
    _, payload = _call(handler.handle_get_job, created["data"]["job"]["id"])
    assert payload["data"]["reboot_required"] is False


def test_list_sources_returns_sources():
    sources = FakeSources()
    sources.sources.append({"id": "acme", "uri": "https://repo.acme.com",
                            "suite": "trixie", "components": "main",
                            "keyring": "/k.gpg"})
    status, payload = _call(_handler(sources=sources).handle_list_sources)
    assert status == 200
    assert payload["data"]["sources"][0]["id"] == "acme"


def test_add_source_creates_it():
    sources = FakeSources()
    status, payload = _call(
        _handler(sources=sources).handle_add_source,
        json={"id": "acme", "uri": "https://repo.acme.com", "suite": "trixie",
              "components": "main", "key": "-----BEGIN PGP PUBLIC KEY BLOCK-----"},
    )
    assert status == 201
    assert payload["data"]["source"]["id"] == "acme"


def test_add_source_missing_body_is_400():
    status, _ = _call(_handler().handle_add_source, json={})
    assert status == 400


def test_add_invalid_source_is_400():
    handler = _handler(sources=FakeSources(raises=InvalidSource("unsigned")))
    status, payload = _call(
        handler.handle_add_source,
        json={"id": "acme", "uri": "https://repo.acme.com", "suite": "trixie",
              "components": "main", "key": "x"},
    )
    assert status == 400
    assert payload["status"] == "error"


def test_remove_source_succeeds():
    sources = FakeSources()
    status, _ = _call(_handler(sources=sources).handle_remove_source, "acme")
    assert status == 200
    assert sources.removed == ["acme"]


def test_remove_unknown_source_is_404():
    handler = _handler(sources=FakeSources(raises=InvalidSource("Unknown source: x")))
    status, _ = _call(handler.handle_remove_source, "nope")
    assert status == 404
