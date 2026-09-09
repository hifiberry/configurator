from configurator.handlers.memory_handler import MemoryHandler


class FakeMemoryInfo:
    def __init__(self):
        self.calls = []

    def collect(self, include_processes=False):
        self.calls.append(include_processes)
        return {"system": {"total_kb": 1}, "features": []}


def test_handler_returns_the_report():
    fake = FakeMemoryInfo()
    payload, status = MemoryHandler(memory_info=fake).get_report(include_processes=False)
    assert status == 200
    assert payload["system"]["total_kb"] == 1
    assert fake.calls == [False]


def test_handler_passes_the_processes_flag():
    fake = FakeMemoryInfo()
    MemoryHandler(memory_info=fake).get_report(include_processes=True)
    assert fake.calls == [True]


def test_handler_reports_collection_failure_as_503():
    class Broken:
        def collect(self, include_processes=False):
            raise OSError("no /proc")

    payload, status = MemoryHandler(memory_info=Broken()).get_report(include_processes=False)
    assert status == 503
    assert payload["status"] == "error"
    assert "no /proc" not in payload["message"]
