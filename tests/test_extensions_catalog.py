from configurator.extensions.catalog import (
    ExtensionCatalog,
    PackageInfo,
    build_extension,
    is_extension_record,
)


def _record(**overrides):
    record = {
        "Package": "hifiberry-tidal-connect",
        "Description": "Tidal Connect endpoint",
        "XB-Hifiberry-Extension": "yes",
        "XB-Extension-Name": "Tidal Connect",
        "XB-Extension-Category": "player",
        "XB-Extension-Needs-Reboot": "maybe",
    }
    record.update(overrides)
    return record


def _info(**overrides):
    kwargs = {
        "name": "hifiberry-tidal-connect",
        "record": _record(),
        "candidate_version": "1.0.2",
        "installed_version": None,
    }
    kwargs.update(overrides)
    return PackageInfo(**kwargs)


def test_marker_yes_is_an_extension():
    assert is_extension_record(_record()) is True


def test_marker_is_case_and_whitespace_tolerant():
    assert is_extension_record(_record(**{"XB-Hifiberry-Extension": " Yes "})) is True


def test_missing_marker_is_not_an_extension():
    record = _record()
    del record["XB-Hifiberry-Extension"]
    assert is_extension_record(record) is False


def test_marker_no_is_not_an_extension():
    assert is_extension_record(_record(**{"XB-Hifiberry-Extension": "no"})) is False


def test_build_extension_maps_fields():
    ext = build_extension(_info())
    assert ext.package == "hifiberry-tidal-connect"
    assert ext.name == "Tidal Connect"
    assert ext.category == "player"
    assert ext.needs_reboot == "maybe"
    assert ext.version == "1.0.2"
    assert ext.state == "available"


def test_build_extension_returns_none_without_marker():
    record = _record()
    del record["XB-Hifiberry-Extension"]
    assert build_extension(_info(record=record)) is None


def test_name_falls_back_to_package_name():
    record = _record()
    del record["XB-Extension-Name"]
    assert build_extension(_info(record=record)).name == "hifiberry-tidal-connect"


def test_unknown_category_falls_back_to_tool():
    record = _record(**{"XB-Extension-Category": "wat"})
    assert build_extension(_info(record=record)).category == "tool"


def test_unknown_needs_reboot_falls_back_to_no():
    record = _record(**{"XB-Extension-Needs-Reboot": "perhaps"})
    assert build_extension(_info(record=record)).needs_reboot == "no"


def test_state_installed_when_versions_match():
    ext = build_extension(_info(installed_version="1.0.2"))
    assert ext.state == "installed"
    assert ext.installed_version == "1.0.2"


def test_state_upgradable_when_installed_differs():
    assert build_extension(_info(installed_version="1.0.1")).state == "upgradable"


def test_description_uses_first_line_as_summary():
    record = _record(Description="Tidal Connect endpoint\n Stream from the Tidal app.")
    ext = build_extension(_info(record=record))
    assert ext.summary == "Tidal Connect endpoint"
    assert "Stream from the Tidal app." in ext.description


def test_catalog_lists_only_extensions():
    packages = [
        _info(),
        _info(name="openssh-server", record={"Package": "openssh-server"}),
    ]
    catalog = ExtensionCatalog(package_source=lambda: packages)
    listed = [e.package for e in catalog.list_extensions()]
    assert listed == ["hifiberry-tidal-connect"]


def test_catalog_get_extension_returns_none_for_non_extension():
    packages = [_info(name="openssh-server", record={"Package": "openssh-server"})]
    catalog = ExtensionCatalog(package_source=lambda: packages)
    assert catalog.get_extension("openssh-server") is None


def test_catalog_get_extension_finds_marked_package():
    catalog = ExtensionCatalog(package_source=lambda: [_info()])
    assert catalog.get_extension("hifiberry-tidal-connect").name == "Tidal Connect"


def test_to_dict_is_json_shaped():
    data = build_extension(_info()).to_dict()
    assert data["package"] == "hifiberry-tidal-connect"
    assert data["state"] == "available"
    assert data["needs_reboot"] == "maybe"
