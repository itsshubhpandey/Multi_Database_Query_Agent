import os
import pickle
from collections import defaultdict

from langgraph.checkpoint.memory import InMemorySaver


class PersistentInMemorySaver(InMemorySaver):
    """
    In-memory checkpointer with simple pickle persistence.
    This keeps LangGraph-compatible storage but writes to disk on updates.
    """

    def __init__(self, path: str, *, serde=None):
        self.path = path
        super().__init__(serde=serde)
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "rb") as f:
                data = pickle.load(f)
            storage = data.get("storage", {})
            writes = data.get("writes", {})
            blobs = data.get("blobs", {})

            self.storage = defaultdict(lambda: defaultdict(dict))
            for thread_id, thread_data in storage.items():
                self.storage[thread_id].update(thread_data)

            self.writes = defaultdict(dict)
            self.writes.update(writes)

            self.blobs = {}
            self.blobs.update(blobs)
        except Exception:
            # If loading fails, start fresh to avoid crashing the agent.
            self.storage = defaultdict(lambda: defaultdict(dict))
            self.writes = defaultdict(dict)
            self.blobs = {}

    def _save(self) -> None:
        data = {
            "storage": dict(self.storage),
            "writes": dict(self.writes),
            "blobs": dict(self.blobs),
        }
        with open(self.path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    def put(self, config, checkpoint, metadata, new_versions):
        result = super().put(config, checkpoint, metadata, new_versions)
        self._save()
        return result

    def put_writes(self, config, writes, task_id, task_path=""):
        result = super().put_writes(config, writes, task_id, task_path=task_path)
        self._save()
        return result

    def delete_thread(self, thread_id: str) -> None:
        super().delete_thread(thread_id)
        self._save()
