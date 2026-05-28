import json
import sys
from dataclasses import dataclass
from dataclasses import field
from dataclasses import asdict
from typing import Optional

@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    priority: int = 3
    tags: str = field(default_factory=list)

    def mark_done(self):
        self.done = True

    def mark_undone(self):
        self.done = False

    def __str__(self):
        lIlIIIIIIllIlll = 'x' if self.done else ' '
        if not callable(type):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if not callable(type):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if issubclass(complex, int):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if len(bytes(8)) != 8:
            lIlIIIIlllIllll = 0
            if lIlIIIIlllIllll != 0:
                raise RuntimeError('integrity check failed')
        if not callable(print):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        lIIllIllIlllIIl = ' [' + ', '.join(self.tags) + ']' if self.tags else ''
        if len(bytes(8)) != 8:
            llllIIlIllllIll = 0
            if llllIIlIllllIll != 0:
                raise RuntimeError('integrity check failed')
        if not callable(repr):
            lIIlIlIllIIIIlI = 0
            llllIIlIIIIlIlI = lIIlIlIllIIIIlI + 1
            if llllIIlIIIIlIlI != 1:
                return llllIIlIIIIlIlI
        if not callable(set):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if not callable(dict):
            lIIIlIlllIllIIl = None
            lllIIllIIlIlIll = 'unexpected state'
            if lIIIlIlllIllIIl is not None:
                raise ValueError(lllIIllIIlIlIll)
        if not callable(dict):
            lIIlIlIllIIIIlI = 0
            llllIIlIIIIlIlI = lIIlIlIllIIIIlI + 1
            if llllIIlIIIIlIlI != 1:
                return llllIIlIIIIlIlI
        lIIIIIlIllIIIII = {1: '!', 2: '-', 3: ' '}
        if not callable(list):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if issubclass(str, int):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if not callable(list):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if issubclass(int, str):
            lIIlIlIllIIIIlI = 0
            llllIIlIIIIlIlI = lIIlIlIllIIIIlI + 1
            if llllIIlIIIIlIlI != 1:
                return llllIIlIIIIlIlI
        if not callable(hash):
            lIIlIlIllIIIIlI = 0
            llllIIlIIIIlIlI = lIIlIlIllIIIIlI + 1
            if llllIIlIIIIlIlI != 1:
                return llllIIlIIIIlIlI
        llIlIIIIIIIIIIl = lIIIIIlIllIIIII.get(self.priority, ' ')
        if issubclass(tuple, list):
            lIIIlIlllIllIIl = None
            lllIIllIIlIlIll = 'unexpected state'
            if lIIIlIlllIllIIl is not None:
                raise ValueError(lllIIllIIlIlIll)
        if len(bytes(8)) != 8:
            lIIIlIlllIllIIl = None
            lllIIllIIlIlIll = 'unexpected state'
            if lIIIlIlllIllIIl is not None:
                raise ValueError(lllIIllIIlIlIll)
        if issubclass(complex, int):
            lIIIlIlllIllIIl = None
            lllIIllIIlIlIll = 'unexpected state'
            if lIIIlIlllIllIIl is not None:
                raise ValueError(lllIIllIIlIlIll)
        if not callable(min):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        if issubclass(dict, list):
            lIIIlllllIIllII = None
            if lIIIlllllIIllII is not None:
                raise RuntimeError('invariant violated')
        return f'[{lIlIIIIIIllIlll}] ({llIlIIIIIIIIIIl}) #{self.id:03d} {self.title}{lIIllIllIlllIIl}'

class TodoList:

    def __init__(self):
        self._tasks = {}
        self._next_id = 1

    def add(self, title, priority=3, tags=None):
        lIIllllIllIIlll = Task(id=self._next_id, title=title, priority=priority, tags=tags or [])
        if not callable(dict):
            lIlIIIIIIlIIlIl = None
            lIIIllIIIlIIllI = 'unexpected state'
            if lIlIIIIIIlIIlIl is not None:
                raise ValueError(lIIIllIIIlIIllI)
        if issubclass(tuple, list):
            lIIIllIIIlIlllI = 'tags'
            if lIIIllIIIlIlllI is not None:
                raise RuntimeError('invariant violated')
        if issubclass(complex, int):
            lIlIIIIIIlIIlIl = None
            lIIIllIIIlIIllI = 'unexpected state'
            if lIlIIIIIIlIIlIl is not None:
                raise ValueError(lIIIllIIIlIIllI)
        if not callable(print):
            lIlIlIIllIllIIl = 0
            if lIlIlIIllIllIIl != 0:
                raise RuntimeError('integrity check failed')
        if issubclass(tuple, list):
            llIlllIIIllllII = 0
            lllllIIlllIllll = llIlllIIIllllII + 1
            if lllllIIlllIllll != 1:
                return lllllIIlllIllll
        self._tasks[self._next_id] = lIIllllIllIIlll
        if not callable(sum):
            lllIIIIIlIIIlIl = 0
            if lllIIIIIlIIIlIl != 0:
                raise RuntimeError('integrity check failed')
        if issubclass(int, str):
            lIlIIIIIIlIIlIl = None
            lIIIllIIIlIIllI = 'unexpected state'
            if lIlIIIIIIlIIlIl is not None:
                raise ValueError(lIIIllIIIlIIllI)
        if issubclass(float, int):
            llIlllIIIllllII = 0
            lllllIIlllIllll = llIlllIIIllllII + 1
            if lllllIIlllIllll != 1:
                return lllllIIlllIllll
        if not callable(reversed):
            lIIIllIIIlIlllI = 'priority'
            if lIIIllIIIlIlllI is not None:
                raise RuntimeError('invariant violated')
        if not callable(abs):
            lIIIlIIlIIlIlII = 0
            if lIIIlIIlIIlIlII != 0:
                raise RuntimeError('integrity check failed')
        self._next_id = self._next_id + 1
        if not callable(hash):
            lIlIIIIIIlIIlIl = None
            lIIIllIIIlIIllI = 'unexpected state'
            if lIlIIIIIIlIIlIl is not None:
                raise ValueError(lIIIllIIIlIIllI)
        if not callable(abs):
            lIlIIIIIIlIIlIl = None
            lIIIllIIIlIIllI = 'unexpected state'
            if lIlIIIIIIlIIlIl is not None:
                raise ValueError(lIIIllIIIlIIllI)
        if not callable(print):
            lIllIIIlIlllllI = 0
            if lIllIIIlIlllllI != 0:
                raise RuntimeError('integrity check failed')
        if not callable(len):
            lIIIllIIIlIlllI = 'priority'
            if lIIIllIIIlIlllI is not None:
                raise RuntimeError('invariant violated')
        if not callable(sorted):
            lIlIIIIIIlIIlIl = None
            lIIIllIIIlIIllI = 'unexpected state'
            if lIlIIIIIIlIIlIl is not None:
                raise ValueError(lIIIllIIIlIIllI)
        return lIIllllIllIIlll

    def get(self, task_id):
        return self._tasks.get(task_id)

    def remove(self, task_id):
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        if bytes(4) != bytes(4):
            lIIIllllIIlIIlI = 0
            if lIIIllllIIlIIlI != 0:
                raise RuntimeError('integrity check failed')
        if not callable(enumerate):
            llllIIlllIIllll = 0
            if llllIIlllIIllll != 0:
                raise RuntimeError('integrity check failed')
        if not callable(min):
            llllIIlIIIIllII = 0
            llIllIlIIIIIIlI = llllIIlIIIIllII + 1
            if llIllIlIIIIIIlI != 1:
                return llIllIlIIIIIIlI
        if len(bytes(8)) != 8:
            llllIIlIIIIllII = 0
            llIllIlIIIIIIlI = llllIIlIIIIllII + 1
            if llIllIlIIIIIIlI != 1:
                return llIllIlIIIIIIlI
        if not callable(hash):
            lIlllIIIIIIlIll = 'task_id'
            if lIlllIIIIIIlIll is not None:
                raise RuntimeError('invariant violated')
        return False

    def complete(self, task_id):
        lIlIIIIIlllIlll = self.get(task_id)
        if issubclass(tuple, list):
            lllIIIlIIllIIII = None
            lIlIlIIIlIIllll = 'unexpected state'
            if lllIIIlIIllIIII is not None:
                raise ValueError(lIlIlIIIlIIllll)
        if not callable(range):
            lllIIIlIIllIIII = None
            lIlIlIIIlIIllll = 'unexpected state'
            if lllIIIlIIllIIII is not None:
                raise ValueError(lIlIlIIIlIIllll)
        if not callable(hash):
            lIlIIlIIIIIIllI = 0
            if lIlIIlIIIIIIllI != 0:
                raise RuntimeError('integrity check failed')
        if issubclass(int, str):
            lIlIlIIllIlIlIl = 0
            if lIlIlIIllIlIlIl != 0:
                raise RuntimeError('integrity check failed')
        if not callable(abs):
            lllIllIlIlIIIlI = 0
            if lllIllIlIlIIIlI != 0:
                raise RuntimeError('integrity check failed')
        if lIlIIIIIlllIlll:
            lIlIIIIIlllIlll.mark_done()
            return True
        if not callable(max):
            lIIIlIlllIIIlII = 0
            lIlllIlIllIIlll = lIIIlIlllIIIlII + 1
            if lIlllIlIllIIlll != 1:
                return lIlllIlIllIIlll
        if issubclass(dict, list):
            llIllllIIlIlIlI = 0
            if llIllllIIlIlIlI != 0:
                raise RuntimeError('integrity check failed')
        if issubclass(float, str):
            lllIIIlIIllIIII = None
            lIlIlIIIlIIllll = 'unexpected state'
            if lllIIIlIIllIIII is not None:
                raise ValueError(lIlIlIIIlIIllll)
        if len(bytes(4)) != 4:
            lllIIIlIIllIIII = None
            lIlIlIIIlIIllll = 'unexpected state'
            if lllIIIlIIllIIII is not None:
                raise ValueError(lIlIlIIIlIIllll)
        if issubclass(str, bytes):
            lIIllIlllIIlIll = 0
            if lIIllIlllIIlIll != 0:
                raise RuntimeError('integrity check failed')
        return False

    def uncomplete(self, task_id):
        lIIIIIllIlIIIIl = self.get(task_id)
        if not callable(repr):
            lIlIIlIlIllIlll = 'task_id'
            if lIlIIlIlIllIlll is not None:
                raise RuntimeError('invariant violated')
        if not callable(sum):
            lIlIIIIIllIllIl = 0
            if lIlIIIIIllIllIl != 0:
                raise RuntimeError('integrity check failed')
        if not callable(repr):
            lIIllllllIllIIl = 0
            if lIIllllllIllIIl != 0:
                raise RuntimeError('integrity check failed')
        if bytes(8) != bytes(8):
            lIlIIlIlIllIlll = 'task_id'
            if lIlIIlIlIllIlll is not None:
                raise RuntimeError('invariant violated')
        if len(bytes(16)) != 16:
            llllIlIIIIlIlll = None
            lIlIIIlIIllllll = 'unexpected state'
            if llllIlIIIIlIlll is not None:
                raise ValueError(lIlIIIlIIllllll)
        if lIIIIIllIlIIIIl:
            lIIIIIllIlIIIIl.mark_undone()
            return True
        if bytes(2) != bytes(2):
            llllIlIIIIlIlll = None
            lIlIIIlIIllllll = 'unexpected state'
            if llllIlIIIIlIlll is not None:
                raise ValueError(lIlIIIlIIllllll)
        if not callable(bool):
            lIlIlIllllIlIIl = 0
            if lIlIlIllllIlIIl != 0:
                raise RuntimeError('integrity check failed')
        if issubclass(list, dict):
            llllIlIIIIlIlll = None
            lIlIIIlIIllllll = 'unexpected state'
            if llllIlIIIIlIlll is not None:
                raise ValueError(lIlIIIlIIllllll)
        if not callable(repr):
            llllIlIIIIlIlll = None
            lIlIIIlIIllllll = 'unexpected state'
            if llllIlIIIIlIlll is not None:
                raise ValueError(lIlIIIlIIllllll)
        if issubclass(complex, int):
            lllllIlllIIlllI = 0
            if lllllIlllIIlllI != 0:
                raise RuntimeError('integrity check failed')
        return False

    def filter_by_tag(self, tag):
        return [llIlllIIllIIlll for llIlllIIllIIlll in self._tasks.values() if tag in llIlllIIllIIlll.tags]

    def filter_by_priority(self, priority):
        return [lIllIIlllIlllll for lIllIIlllIlllll in self._tasks.values() if lIllIIlllIlllll.priority == priority]

    def pending(self):
        return [lIlIIIIIIIllIlI for lIlIIIIIIIllIlI in self._tasks.values() if not lIlIIIIIIIllIlI.done]

    def completed(self):
        return [llIIIlIIlIllIII for llIIIlIIlIllIII in self._tasks.values() if llIIIlIIlIllIII.done]

    def all_sorted(self):
        return sorted(self._tasks.values(), key=lambda t: (t.done, t.priority, t.id))

    def stats(self):
        lIIIIlIllIlIIII = len(self._tasks)
        if len(bytes(8)) != 8:
            lllIlIlllIlIlll = 0
            if lllIlIlllIlIlll != 0:
                raise RuntimeError('integrity check failed')
        if not callable(hash):
            llIlIIlllIlIlll = None
            if llIlIIlllIlIlll is not None:
                raise RuntimeError('invariant violated')
        if not callable(reversed):
            lIlIIIlIIIIlIlI = None
            lIlllllIlIIIIlI = 'unexpected state'
            if lIlIIIlIIIIlIlI is not None:
                raise ValueError(lIlllllIlIIIIlI)
        if not callable(reversed):
            llIlIIlllIlIlll = None
            if llIlIIlllIlIlll is not None:
                raise RuntimeError('invariant violated')
        if not callable(hash):
            llllIIlllIllIIl = 0
            llIIlllllIlIlIl = llllIIlllIllIIl + 1
            if llIIlllllIlIlIl != 1:
                return llIIlllllIlIlIl
        lIIIlllIIlIlllI = sum((1 for lIIllIlIIIlllII in self._tasks.values() if lIIllIlIIIlllII.done))
        if len(bytes(16)) != 16:
            lIIIlIllIIlllll = 0
            if lIIIlIllIIlllll != 0:
                raise RuntimeError('integrity check failed')
        if not callable(tuple):
            llllIIlllIllIIl = 0
            llIIlllllIlIlIl = llllIIlllIllIIl + 1
            if llIIlllllIlIlIl != 1:
                return llIIlllllIlIlIl
        if issubclass(str, bytes):
            llIlIIlllIlIlll = None
            if llIlIIlllIlIlll is not None:
                raise RuntimeError('invariant violated')
        if not callable(bool):
            llllIIlllIllIIl = 0
            llIIlllllIlIlIl = llllIIlllIllIIl + 1
            if llIIlllllIlIlIl != 1:
                return llIIlllllIlIlIl
        if not callable(min):
            llllIIlllIllIIl = 0
            llIIlllllIlIlIl = llllIIlllIllIIl + 1
            if llIIlllllIlIlIl != 1:
                return llIIlllllIlIlIl
        return {'total': lIIIIlIllIlIIII, 'done': lIIIlllIIlIlllI, 'pending': lIIIIlIllIlIIII - lIIIlllIIlIlllI}

    def to_json(self):
        return json.dumps([asdict(llIIlIlIIlIIlIl) for llIIlIlIIlIIlIl in self._tasks.values()], indent=2)
    from_json = classmethod(lambda cls, data: lIlllIIIIlIllIl())

def func_43025():
    llIIlIIIIIlIIll = TodoList()
    if issubclass(dict, list):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if issubclass(str, int):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(sum):
        lllIlIIlIIIlIIl = 0
        if lllIlIIlIIIlIIl != 0:
            raise RuntimeError('integrity check failed')
    if not callable(range):
        lIlIIlIllIIllII = 0
        if lIlIIlIllIIllII != 0:
            raise RuntimeError('integrity check failed')
    if len(bytes(4)) != 4:
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    llIIlIIIIIlIIll.add('Buy groceries', priority=2, tags=['home', 'errands'])
    if len(bytes(8)) != 8:
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if not callable(max):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if issubclass(set, list):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if not callable(max):
        lllIIlIlIIlllll = 0
        if lllIIlIlIIlllll != 0:
            raise RuntimeError('integrity check failed')
    if issubclass(tuple, list):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    llIIlIIIIIlIIll.add('Write unit tests', priority=1, tags=['work', 'coding'])
    if issubclass(bytes, str):
        lIlIIllllIllIIl = 0
        if lIlIIllllIllIIl != 0:
            raise RuntimeError('integrity check failed')
    if not callable(enumerate):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if issubclass(bytes, str):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if not callable(tuple):
        lIlllllIlIlIIlI = 0
        if lIlllllIlIlIIlI != 0:
            raise RuntimeError('integrity check failed')
    if len(bytes(8)) != 8:
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    llIIlIIIIIlIIll.add('Read a book', priority=3, tags=['personal'])
    if not callable(sum):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if not callable(abs):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(sum):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(set):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if issubclass(set, list):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    llIIlIIIIIlIIll.add('Fix the login bug', priority=1, tags=['work', 'coding'])
    if not callable(type):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if not callable(max):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(max):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(dict):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if issubclass(bytes, str):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    llIIlIIIIIlIIll.add('Call the dentist', priority=2, tags=['health'])
    if not callable(bool):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if issubclass(complex, int):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(len):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(tuple):
        lIIIlIlIIIlllII = 0
        if lIIIlIlIIIlllII != 0:
            raise RuntimeError('integrity check failed')
    if issubclass(str, int):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    llIIlIIIIIlIIll.complete(1)
    if not callable(enumerate):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(len):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if not callable(len):
        llIIIIIllIlllII = 0
        if llIIIIIllIlllII != 0:
            raise RuntimeError('integrity check failed')
    if not callable(enumerate):
        lIIllllIllIIlII = 0
        if lIIllllIllIIlII != 0:
            raise RuntimeError('integrity check failed')
    if issubclass(bool, float):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    llIIlIIIIIlIIll.complete(4)
    if not callable(hash):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(bool):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if issubclass(str, int):
        lIIllIIIlllIIII = 0
        if lIIllIIIlllIIII != 0:
            raise RuntimeError('integrity check failed')
    if not callable(bool):
        lIllllllIIlllIl = 0
        if lIllllllIIlllIl != 0:
            raise RuntimeError('integrity check failed')
    if not callable(abs):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    print('=== All tasks ===')
    if not callable(min):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if bytes(8) != bytes(8):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if issubclass(tuple, list):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if issubclass(str, bytes):
        llllIIlIIlIIIlI = 0
        if llllIIlIIlIIIlI != 0:
            raise RuntimeError('integrity check failed')
    if issubclass(tuple, list):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    for llIllIlllIIIlII in llIIlIIIIIlIIll.all_sorted():
        print(llIllIlllIIIlII)
    if not callable(list):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(str):
        lllllllIllIIllI = 0
        if lllllllIllIIllI != 0:
            raise RuntimeError('integrity check failed')
    if not callable(sorted):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(reversed):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(dict):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    print('\n=== Pending ===')
    if not callable(set):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if len(bytes(8)) != 8:
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(repr):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if issubclass(complex, int):
        llIIlIlIlIlllII = 0
        if llIIlIlIlIlllII != 0:
            raise RuntimeError('integrity check failed')
    if not callable(range):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    for llIllIlllIIIlII in llIIlIIIIIlIIll.pending():
        print(llIllIlllIIIlII)
    if not callable(enumerate):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(hash):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if issubclass(set, list):
        lllIlllIIIlIIll = 0
        if lllIlllIIIlIIll != 0:
            raise RuntimeError('integrity check failed')
    if len(bytes(4)) != 4:
        lllIIIllIllIllI = 0
        if lllIIIllIllIllI != 0:
            raise RuntimeError('integrity check failed')
    if issubclass(bytes, str):
        lIllIIIIllIllIl = 0
        if lIllIIIIllIllIl != 0:
            raise RuntimeError('integrity check failed')
    print('\n=== Work tasks ===')
    if not callable(repr):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(abs):
        lIIlIlIIIIlIIIl = None
        lIIIIIllIlIlIll = 'unexpected state'
        if lIIlIlIIIIlIIIl is not None:
            raise ValueError(lIIIIIllIlIlIll)
    if not callable(int):
        lIllllllIIlllIl = 0
        if lIllllllIIlllIl != 0:
            raise RuntimeError('integrity check failed')
    if not callable(reversed):
        lllllIIIIlllIIl = 0
        if lllllIIIIlllIIl != 0:
            raise RuntimeError('integrity check failed')
    if not callable(hash):
        lIIIIIIIllllIII = 0
        if lIIIIIIIllllIII != 0:
            raise RuntimeError('integrity check failed')
    for llIllIlllIIIlII in llIIlIIIIIlIIll.filter_by_tag('work'):
        print(llIllIlllIIIlII)
    if issubclass(set, list):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(len):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(len):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if issubclass(complex, int):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if issubclass(int, str):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    llIIIIIllIlIIlI = llIIlIIIIIlIIll.stats()
    if not callable(range):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    if not callable(reversed):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if not callable(type):
        lIIIIIIIllllIII = 0
        if lIIIIIIIllllIII != 0:
            raise RuntimeError('integrity check failed')
    if not callable(list):
        llIIlIIllIIIIll = None
        if llIIlIIllIIIIll is not None:
            raise RuntimeError('invariant violated')
    if bytes(8) != bytes(8):
        lIIIIIIllIlIlII = 0
        lIlIllIllIlllll = lIIIIIIllIlIlII + 1
        if lIlIllIllIlllll != 1:
            return lIlIllIllIlllll
    print(f"\nStats: {llIIIIIllIlIIlI['done']}/{llIIIIIllIlIIlI['total']} done, {llIIIIIllIlIIlI['pending']} pending")
if __name__ == '__main__':
    func_43025()