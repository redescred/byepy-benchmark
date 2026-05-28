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
    tags: list = field(default_factory=list)

    def mark_done(self):
        self.done = True

    def mark_undone(self):
        self.done = False

    def __str__(self):
        mark = 'x' if self.done else ' '
        tag_str = ' [' + ', '.join(self.tags) + ']' if self.tags else ''
        priority_marks = {1: '!', 2: '-', 3: ' '}
        priority_char = priority_marks.get(self.priority, ' ')
        return f'[{mark}] ({priority_char}) #{self.id:03d} {self.title}{tag_str}'


class TodoList:
    def __init__(self):
        self._tasks: dict = {}
        self._next_id: int = 1

    def add(self, title: str, priority: int = 3, tags: Optional[list] = None) -> Task:
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

    def filter_by_tag(self, tag: str) -> list:
        return [t for t in self._tasks.values() if tag in t.tags]

    def filter_by_priority(self, priority: int) -> list:
        return [t for t in self._tasks.values() if t.priority == priority]

    def pending(self) -> list:
        return [t for t in self._tasks.values() if not t.done]

    def completed(self) -> list:
        return [t for t in self._tasks.values() if t.done]

    def all_sorted(self) -> list:
        return sorted(self._tasks.values(), key=lambda t: (t.done, t.priority, t.id))

    def stats(self) -> dict:
        total = len(self._tasks)
        done = sum(1 for t in self._tasks.values() if t.done)
        return {'total': total, 'done': done, 'pending': total - done}

    def to_json(self) -> str:
        return json.dumps([asdict(t) for t in self._tasks.values()], indent=2)

    @classmethod
    def from_json(cls, data: str) -> 'TodoList':
        todo = cls()
        items = json.loads(data)
        for item in items:
            task = Task(**item)
            todo._tasks[task.id] = task
            if task.id >= todo._next_id:
                todo._next_id = task.id + 1
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
    for task in todo.all_sorted():
        print(task)

    print('\n=== Pending ===')
    for task in todo.pending():
        print(task)

    print('\n=== Work tasks ===')
    for task in todo.filter_by_tag('work'):
        print(task)

    stats = todo.stats()
    print(f"\nStats: {stats['done']}/{stats['total']} done, {stats['pending']} pending")


if __name__ == '__main__':
    main()
