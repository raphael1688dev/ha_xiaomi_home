"""Storage writes are atomic and never overlap for one file."""
# pylint: disable=protected-access
import asyncio
import os
import threading
import time

import pytest

from custom_components.xiaomi_home.miot.miot_storage import MIoTStorage


@pytest.mark.asyncio
async def test_saves_to_one_file_do_not_overlap(tmp_path, monkeypatch) -> None:
    """Two callers waiting on the same pending save both started writing
    when it finished."""
    storage = MIoTStorage(str(tmp_path))
    active, overlaps = [0], [0]
    lock = threading.Lock()
    save = storage._MIoTStorage__save

    def slow_save(*args, **kwargs):
        with lock:
            active[0] += 1
            overlaps[0] = max(overlaps[0], active[0])
        time.sleep(0.05)
        try:
            return save(*args, **kwargs)
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(storage, "_MIoTStorage__save", slow_save)
    results = await asyncio.gather(*(
        storage.save_async("d", "n", {"i": i}) for i in range(5)))

    assert all(results)
    assert overlaps[0] == 1
    assert await storage.load_async("d", "n", dict) in (
        {"i": i} for i in range(5))


@pytest.mark.asyncio
async def test_save_replaces_the_file_atomically(tmp_path) -> None:
    storage = MIoTStorage(str(tmp_path))
    assert await storage.save_async("d", "n", {"a": 1})
    assert await storage.save_async("d", "n", {"a": 2})
    assert await storage.load_async("d", "n", dict) == {"a": 2}
    assert not [f for f in os.listdir(tmp_path / "d") if f.endswith(".tmp")]
