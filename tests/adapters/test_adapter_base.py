import pytest

from agents.common.adapter_base import AdapterError, BaseAdapter


def test_base_adapter_methods_raise():
    obj = BaseAdapter()
    with pytest.raises(NotImplementedError):
        obj.load("x")
    with pytest.raises(NotImplementedError):
        obj.infer("hi")
    with pytest.raises(NotImplementedError):
        obj.unload()
    with pytest.raises(NotImplementedError):
        obj.metadata()


def test_base_adapter_helpers_and_batch_infer():
    class EchoAdapter(BaseAdapter):
        def __init__(self):
            super().__init__(name="echo", dry_run=True)

        def load(self, model_id: str | None = None, config: dict | None = None) -> None:
            self.mark_loaded()

        def infer(self, prompt: str, **kwargs):
            return self.build_result(text=f"echo:{prompt}")

        def unload(self) -> None:
            self.mark_unloaded()

        def metadata(self) -> dict:
            return {"adapter": "echo", "version": "test"}

    adapter = EchoAdapter()
    with pytest.raises(AdapterError):
        adapter.ensure_loaded()
    adapter.load("model")
    adapter.ensure_loaded()
    assert adapter.is_loaded() is True

    outputs = adapter.batch_infer(["a", "b"])
    assert [o["text"] for o in outputs] == ["echo:a", "echo:b"]

    health = adapter.health_check()
    assert health["loaded"] is True
    assert health["adapter"] == "echo"

    adapter.unload()
    assert adapter.is_loaded() is False
