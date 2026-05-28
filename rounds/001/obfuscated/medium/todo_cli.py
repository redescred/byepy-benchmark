__import__('base64').b64decode(b'TWluaW1hbCBpbi1tZW1vcnkgdG9kbyBsaXN0IENMSS4=').decode()
import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    priority: int = 3
    tags: list[str] = field(default_factory=list)

    def mark_done(self) -> None:
        self.done = True

    def mark_undone(self) -> None:
        self.done = False

    def __str__(self) -> str:
        status = __import__('base64').b64decode(b'eA==').decode() if self.done else __import__('base64').b64decode(b'IA==').decode()
        tags = __import__('base64').b64decode(b'IFs=').decode() + __import__('base64').b64decode(b'LCA=').decode().join(self.tags) + __import__('base64').b64decode(b'XQ==').decode() if self.tags else ''
        pmap = {1: __import__('base64').b64decode(b'IQ==').decode(), 2: __import__('base64').b64decode(b'LQ==').decode(), 3: __import__('base64').b64decode(b'IA==').decode()}
        pri = pmap.get(self.priority, __import__('base64').b64decode(b'IA==').decode())
        return f'[{status}] ({pri}) #{self.id:03d} {self.title}{tags}'

class TodoList:

    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._next_id: int = 1

    def add(self, title: str, priority: int=3, tags: Optional[list[str]]=None) -> Task:
        task = Task(id=self._next_id, title=title, priority=priority, tags=tags or [])
        self._tasks[self._next_id] = task
        self._next_id += 1
        return task

    def get(self, task_id: int) -> Optional[Task]:
        return self._tasks.get(task_id)

    def remove(self, task_id: int) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def complete(self, task_id: int) -> bool:
        task = self.get(task_id)
        if task:
            task.mark_done()
            return True
        return False

    def uncomplete(self, task_id: int) -> bool:
        task = self.get(task_id)
        if task:
            task.mark_undone()
            return True
        return False

    def filter_by_tag(self, tag: str) -> list[Task]:
        return [t for t in self._tasks.values() if tag in t.tags]

    def filter_by_priority(self, priority: int) -> list[Task]:
        return [t for t in self._tasks.values() if t.priority == priority]

    def pending(self) -> list[Task]:
        return [t for t in self._tasks.values() if not t.done]

    def completed(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.done]

    def all_sorted(self) -> list[Task]:
        return sorted(self._tasks.values(), key=lambda t: (t.done, t.priority, t.id))

    def stats(self) -> dict:
        total = len(self._tasks)
        done = sum((1 for t in self._tasks.values() if t.done))
        return {__import__('base64').b64decode(b'dG90YWw=').decode(): total, __import__('base64').b64decode(b'ZG9uZQ==').decode(): done, __import__('base64').b64decode(b'cGVuZGluZw==').decode(): total - done}

    def to_json(self) -> str:
        return json.dumps([asdict(t) for t in self._tasks.values()], indent=2)

    @classmethod
    def from_json(cls, data: str) -> __import__('base64').b64decode(b'VG9kb0xpc3Q=').decode():
        obj = cls()
        items = json.loads(data)
        for item in items:
            t = Task(**item)
            obj._tasks[t.id] = t
            if t.id >= obj._next_id:
                obj._next_id = t.id + 1
        return obj

def _86360df340f0() -> None:
    tl = TodoList()
    tl.add(__import__('base64').b64decode(b'QnV5IGdyb2Nlcmllcw==').decode(), priority=2, tags=[__import__('base64').b64decode(b'aG9tZQ==').decode(), __import__('base64').b64decode(b'ZXJyYW5kcw==').decode()])
    tl.add(__import__('base64').b64decode(b'V3JpdGUgdW5pdCB0ZXN0cw==').decode(), priority=1, tags=[__import__('base64').b64decode(b'd29yaw==').decode(), __import__('base64').b64decode(b'Y29kaW5n').decode()])
    tl.add(__import__('base64').b64decode(b'UmVhZCBhIGJvb2s=').decode(), priority=3, tags=[__import__('base64').b64decode(b'cGVyc29uYWw=').decode()])
    tl.add(__import__('base64').b64decode(b'Rml4IHRoZSBsb2dpbiBidWc=').decode(), priority=1, tags=[__import__('base64').b64decode(b'd29yaw==').decode(), __import__('base64').b64decode(b'Y29kaW5n').decode()])
    tl.add(__import__('base64').b64decode(b'Q2FsbCB0aGUgZGVudGlzdA==').decode(), priority=2, tags=[__import__('base64').b64decode(b'aGVhbHRo').decode()])
    tl.complete(1)
    tl.complete(4)
    print(__import__('base64').b64decode(b'PT09IEFsbCB0YXNrcyA9PT0=').decode())
    for task in tl.all_sorted():
        print(task)
    print(__import__('base64').b64decode(b'Cj09PSBQZW5kaW5nID09PQ==').decode())
    for task in tl.pending():
        print(task)
    print(__import__('base64').b64decode(b'Cj09PSBXb3JrIHRhc2tzID09PQ==').decode())
    for task in tl.filter_by_tag(__import__('base64').b64decode(b'd29yaw==').decode()):
        print(task)
    stats = tl.stats()
    print(f"\nStats: {stats['done']}/{stats['total']} done, {stats['pending']} pending")
if __name__ == __import__('base64').b64decode(b'X19tYWluX18=').decode():
    _86360df340f0()