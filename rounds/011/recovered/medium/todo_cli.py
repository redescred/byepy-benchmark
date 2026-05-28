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
        lIlIIIIlllIllll = ' [' + ', '.join(self.tags) + ']' if self.tags else ''
        llllIIlIllllIll = {1: '!', 2: '-', 3: ' '}
        lIIlIlIllIIIIlI = llllIIlIllllIll.get(self.priority, ' ')
        return f'[{lIlIIIIIIllIlll}] ({lIIlIlIllIIIIlI}) #{self.id:03d} {self.title}{lIlIIIIlllIllll}'

class TodoList:

    def __init__(self):
        self._tasks = {}
        self._next_id = 1

    def add(self, title, priority=3, tags=None):
        lIIllllIllIIlll = Task(id=self._next_id, title=title, priority=priority, tags=tags or [])
        self._tasks[self._next_id] = lIIllllIllIIlll
        self._next_id = self._next_id + 1
        return lIIllllIllIIlll

    def get(self, task_id):
        return self._tasks.get(task_id)

    def remove(self, task_id):
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def complete(self, task_id):
        lIlIIIIIlllIlll = self.get(task_id)
        if lIlIIIIIlllIlll:
            lIlIIIIIlllIlll.mark_done()
            return True
        return False

    def uncomplete(self, task_id):
        lIIIIIllIlIIIIl = self.get(task_id)
        if lIIIIIllIlIIIIl:
            lIIIIIllIlIIIIl.mark_undone()
            return True
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
        llIlIIlllIlIlll = sum((1 for lIIllIlIIIlllII in self._tasks.values() if lIIllIlIIIlllII.done))
        return {'total': lIIIIlIllIlIIII, 'done': llIlIIlllIlIlll, 'pending': lIIIIlIllIlIIII - llIlIIlllIlIlll}

    def to_json(self):
        return json.dumps([asdict(llIIlIlIIlIIlIl) for llIIlIlIIlIIlIl in self._tasks.values()], indent=2)
    from_json = classmethod(lambda cls, data: lllIIIlIIlIIIIl)

def func_43025():
    llIIlIIIIIlIIll = TodoList()
    llIIlIIIIIlIIll.add('Buy groceries', priority=2, tags=['home', 'errands'])
    llIIlIIIIIlIIll.add('Write unit tests', priority=1, tags=['work', 'coding'])
    llIIlIIIIIlIIll.add('Read a book', priority=3, tags=['personal'])
    llIIlIIIIIlIIll.add('Fix the login bug', priority=1, tags=['work', 'coding'])
    llIIlIIIIIlIIll.add('Call the dentist', priority=2, tags=['health'])
    llIIlIIIIIlIIll.complete(1)
    llIIlIIIIIlIIll.complete(4)
    print('=== All tasks ===')
    for lIlIIllllIllIIl in llIIlIIIIIlIIll.all_sorted():
        print(lIlIIllllIllIIl)
    print('\n=== Pending ===')
    for lIlIIllllIllIIl in llIIlIIIIIlIIll.pending():
        print(lIlIIllllIllIIl)
    print('\n=== Work tasks ===')
    for lIlIIllllIllIIl in llIIlIIIIIlIIll.filter_by_tag('work'):
        print(lIlIIllllIllIIl)
    lIlllllIlIlIIlI = llIIlIIIIIlIIll.stats()
    print(f"\nStats: {lIlllllIlIlIIlI['done']}/{lIlllllIlIlIIlI['total']} done, {lIlllllIlIlIIlI['pending']} pending")
if __name__ == '__main__':
    func_43025()