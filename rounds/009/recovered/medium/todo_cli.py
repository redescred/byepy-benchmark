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
        status_char = 'x' if self.done else ' '
        tags_str = ' [' + ', '.join(self.tags) + ']' if self.tags else ''
        priority_symbols = {1: '!', 2: '-', 3: ' '}
        priority_char = priority_symbols.get(self.priority, ' ')
        return f'[{status_char}] ({priority_char}) #{self.id:03d} {self.title}{tags_str}'

class TodoList:

    def __init__(self):
        self._tasks = {}
        self._next_id = 1

    def add(self, title, priority=3, tags=None):
        task = Task(id=self._next_id, title=title, priority=priority, tags=tags or [])
        self._tasks[self._next_id] = task
        self._next_id = self._next_id + 1
        return task

    def get(self, task_id):
        return self._tasks.get(task_id)

    def remove(self, task_id):
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def complete(self, task_id):
        task = self.get(task_id)
        if task:
            task.mark_done()
            return True
        return False

    def uncomplete(self, task_id):
        task = self.get(task_id)
        if task:
            task.mark_undone()
            return True
        return False

    def filter_by_tag(self, tag):
        return [t for t in self._tasks.values() if tag in t.tags]

    def filter_by_priority(self, priority):
        return [t for t in self._tasks.values() if t.priority == priority]

    def pending(self):
        return [t for t in self._tasks.values() if not t.done]

    def completed(self):
        return [t for t in self._tasks.values() if t.done]

    def all_sorted(self):
        return sorted(self._tasks.values(), key=lambda t: (t.done, t.priority, t.id))

    def stats(self):
        total = len(self._tasks)
        done_count = sum((1 for t in self._tasks.values() if t.done))
        return {'total': total, 'done': done_count, 'pending': total - done_count}

    def to_json(self):
        return json.dumps([asdict(t) for t in self._tasks.values()], indent=2)

    @classmethod
    def from_json(cls, data):
        todo = cls()
        for item in json.loads(data):
            t = Task(**item)
            todo._tasks[t.id] = t
            todo._next_id = max(todo._next_id, t.id + 1)
        return todo

def main():
    todo = TodoList()
    todo.add('Buy groceries', priority=2, tags=['home', 'errands'])
    todo.add('Write unit tests', priority=1, tags=['work', 'coding'])
    todo.add('Read a book', priority=3, tags=['personal'])
    todo.add('Fix the login bug', priority=1, tags=['work', 'coding'])
    todo.add('Call the dentist', priority=2, tags=['health'])
    todo.complete(1)
    todo.complete(4)
    print('=== All tasks ===')
    for t in todo.all_sorted():
        print(t)
    print('\n=== Pending ===')
    for t in todo.pending():
        print(t)
    print('\n=== Work tasks ===')
    for t in todo.filter_by_tag('work'):
        print(t)
    s = todo.stats()
    print(f"\nStats: {s['done']}/{s['total']} done, {s['pending']} pending")
if __name__ == '__main__':
    main()