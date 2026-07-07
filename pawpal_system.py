"""
PawPal+ core system.

This module contains no UI code on purpose. It is designed to be fully
testable and runnable from a CLI (see demo.py) before ever being wired
into the Streamlit app (app.py).

Class overview (see diagrams/uml.mmd for the full picture):
    Owner       - a pet owner with a daily available time window
    Pet         - belongs to an Owner, has a list of Tasks
    Task        - base class for a care activity (abstract-ish; use subclasses)
    Walk, Feeding, Medication, Appointment - Task subclasses
    ScheduledTask - a Task placed at a specific time in a plan
    DailyPlan   - the output of the scheduler for one pet on one day
    Scheduler   - stateless engine that sorts tasks, finds conflicts,
                  expands recurring tasks, and builds a DailyPlan
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from enum import Enum, IntEnum
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Priority(IntEnum):
    """Higher number = higher priority. IntEnum lets us sort/compare directly."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Recurrence(Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class Task:
    """Base class for any pet care activity.

    A Task is either "flexible" (no preferred_time -- the scheduler decides
    when it happens) or "fixed-time" (preferred_time is set -- e.g. a vet
    appointment that must happen at 2:00 PM).
    """

    def __init__(
        self,
        title: str,
        duration_minutes: int,
        priority: Priority = Priority.MEDIUM,
        recurrence: Recurrence = Recurrence.NONE,
        preferred_time: Optional[time] = None,
        day_of_week: Optional[int] = None,
        notes: str = "",
    ):
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")

        self.task_id = str(uuid.uuid4())[:8]
        self.title = title
        self.duration_minutes = duration_minutes
        self.priority = priority
        self.recurrence = recurrence
        self.preferred_time = preferred_time
        # only meaningful when recurrence == WEEKLY. 0=Monday ... 6=Sunday.
        self.day_of_week = day_of_week
        self.notes = notes
        self.completed = False

    @property
    def is_fixed_time(self) -> bool:
        return self.preferred_time is not None

    def get_end_time(self, start: Optional[time] = None) -> Optional[time]:
        """Return the end time given a start time (defaults to preferred_time)."""
        start = start if start is not None else self.preferred_time
        if start is None:
            return None
        start_dt = datetime.combine(date.today(), start)
        end_dt = start_dt + timedelta(minutes=self.duration_minutes)
        return end_dt.time()

    def conflicts_with(self, other: "Task") -> bool:
        """Two tasks conflict only if BOTH have a fixed preferred_time and
        their time ranges overlap. Flexible tasks never "conflict" -- the
        scheduler just sequences them, it doesn't need to reject them.
        """
        if not self.is_fixed_time or not other.is_fixed_time:
            return False
        a_start = datetime.combine(date.today(), self.preferred_time)
        a_end = a_start + timedelta(minutes=self.duration_minutes)
        b_start = datetime.combine(date.today(), other.preferred_time)
        b_end = b_start + timedelta(minutes=other.duration_minutes)
        return a_start < b_end and b_start < a_end

    def is_due_on(self, target_date: date) -> bool:
        """Whether this task should be considered for scheduling on target_date."""
        if self.completed and self.recurrence == Recurrence.NONE:
            return False
        if self.recurrence == Recurrence.WEEKLY:
            return self.day_of_week is None or self.day_of_week == target_date.weekday()
        return True  # NONE and DAILY are due every day they're active

    def icon(self) -> str:
        return "*"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.title}' {self.duration_minutes}min {self.priority.name}>"


class Walk(Task):
    def icon(self) -> str:
        return "W"


class Feeding(Task):
    def icon(self) -> str:
        return "F"


class Medication(Task):
    """Medications default to HIGH priority since missing a dose matters more
    than missing a walk."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("priority", Priority.HIGH)
        super().__init__(*args, **kwargs)

    def icon(self) -> str:
        return "M"


class Appointment(Task):
    """Appointments must have a fixed time -- there's no such thing as a
    flexible vet visit."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("priority", Priority.HIGH)
        super().__init__(*args, **kwargs)
        if self.preferred_time is None:
            raise ValueError("Appointment requires a preferred_time")

    def icon(self) -> str:
        return "A"


# ---------------------------------------------------------------------------
# People / pets
# ---------------------------------------------------------------------------

class Owner:
    def __init__(self, name: str, day_start: time = time(7, 0), day_end: time = time(21, 0)):
        self.name = name
        self.day_start = day_start
        self.day_end = day_end
        self.pets: List["Pet"] = []

    def add_pet(self, pet: "Pet") -> "Pet":
        pet.owner = self
        self.pets.append(pet)
        return pet


class Pet:
    def __init__(self, name: str, species: str, breed: str = "", owner: Optional[Owner] = None):
        self.name = name
        self.species = species
        self.breed = breed
        self.owner = owner
        self.tasks: List[Task] = []

    def add_task(self, task: Task) -> Task:
        self.tasks.append(task)
        return task

    def remove_task(self, task_id: str) -> bool:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.task_id != task_id]
        return len(self.tasks) < before

    def tasks_by_type(self, task_cls) -> List[Task]:
        return [t for t in self.tasks if isinstance(t, task_cls)]


# ---------------------------------------------------------------------------
# Scheduling output
# ---------------------------------------------------------------------------

class ScheduledTask:
    def __init__(self, task: Task, start_time: time, end_time: time, reason: str):
        self.task = task
        self.start_time = start_time
        self.end_time = end_time
        self.reason = reason

    def __repr__(self) -> str:
        return (
            f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')} "
            f"{self.task.title} ({self.task.priority.name})"
        )


class DailyPlan:
    def __init__(self, pet: Pet, plan_date: date):
        self.pet = pet
        self.date = plan_date
        self.scheduled_items: List[ScheduledTask] = []
        self.unscheduled_tasks: List[Tuple[Task, str]] = []

    def add_item(self, scheduled_task: ScheduledTask) -> None:
        self.scheduled_items.append(scheduled_task)

    def add_unscheduled(self, task: Task, reason: str) -> None:
        self.unscheduled_tasks.append((task, reason))

    def total_minutes_used(self) -> int:
        return sum(item.task.duration_minutes for item in self.scheduled_items)

    def summary(self) -> str:
        lines = [f"Daily plan for {self.pet.name} ({self.pet.species}) -- {self.date.isoformat()}"]
        if not self.scheduled_items:
            lines.append("  No tasks scheduled.")
        for item in self.scheduled_items:
            lines.append(
                f"  {item.start_time.strftime('%H:%M')} -- {item.task.title} "
                f"({item.task.duration_minutes} min) [priority: {item.task.priority.name.lower()}] "
                f"-- {item.reason}"
            )
        if self.unscheduled_tasks:
            lines.append("  Could not fit:")
            for task, reason in self.unscheduled_tasks:
                lines.append(f"    - {task.title}: {reason}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """Stateless scheduling engine. Every method is a pure function of its
    inputs so it's easy to unit test in isolation."""

    @staticmethod
    def sort_tasks(tasks: List[Task]) -> List[Task]:
        """Sort by priority (HIGH first), then by duration (shortest first).

        Tradeoff: sorting shorter tasks first within the same priority tier
        means we generally fit MORE tasks into the available time, at the
        cost of possibly delaying a longer high-value task. For a pet care
        app, fitting more of the day's routine in feels like the right
        default -- see reflection.md for why you might change this.
        """
        return sorted(tasks, key=lambda t: (-t.priority.value, t.duration_minutes))

    @staticmethod
    def detect_conflicts(tasks: List[Task]) -> List[Tuple[Task, Task]]:
        """Return all pairs of fixed-time tasks whose time ranges overlap."""
        conflicts = []
        fixed = [t for t in tasks if t.is_fixed_time]
        for i in range(len(fixed)):
            for j in range(i + 1, len(fixed)):
                if fixed[i].conflicts_with(fixed[j]):
                    conflicts.append((fixed[i], fixed[j]))
        return conflicts

    @staticmethod
    def expand_recurring(tasks: List[Task], target_date: date) -> List[Task]:
        """Filter a pet's full task list down to what's actually due today."""
        return [t for t in tasks if t.is_due_on(target_date)]

    @staticmethod
    def build_daily_plan(pet: Pet, target_date: date, owner: Optional[Owner] = None) -> DailyPlan:
        """Build a full day's plan for a pet.

        Algorithm:
        1. Expand recurring tasks to find what's due today.
        2. Split into fixed-time tasks (Appointment/Medication with a set
           time) and flexible tasks (everything else).
        3. Resolve conflicts among fixed-time tasks: the higher-priority
           task wins, the loser goes to unscheduled_tasks.
        4. Drop fixed tasks that fall outside the owner's available hours.
        5. Walk through the day in order: fill the gap before each fixed
           task with as many flexible tasks as fit (highest priority
           first), place the fixed task, then repeat. Any flexible tasks
           left over at the end of the day are unscheduled.
        """
        owner = owner or pet.owner
        if owner is None:
            raise ValueError("Pet must have an owner (directly or passed in) to build a plan")

        plan = DailyPlan(pet, target_date)
        due_tasks = Scheduler.expand_recurring(pet.tasks, target_date)

        fixed_tasks = sorted(
            [t for t in due_tasks if t.is_fixed_time], key=lambda t: t.preferred_time
        )
        flexible_tasks = Scheduler.sort_tasks([t for t in due_tasks if not t.is_fixed_time])

        # --- resolve conflicts among fixed tasks ---
        accepted_fixed: List[Task] = []
        for t in fixed_tasks:
            conflict = next((a for a in accepted_fixed if t.conflicts_with(a)), None)
            if conflict is None:
                accepted_fixed.append(t)
            elif t.priority > conflict.priority:
                accepted_fixed.remove(conflict)
                accepted_fixed.append(t)
                plan.add_unscheduled(conflict, f"conflicts with '{t.title}' (lower priority)")
            else:
                plan.add_unscheduled(t, f"conflicts with '{conflict.title}' (lower priority)")
        accepted_fixed.sort(key=lambda t: t.preferred_time)

        # --- drop fixed tasks outside the owner's available window ---
        in_window_fixed = []
        for t in accepted_fixed:
            end_time = t.get_end_time()
            if t.preferred_time < owner.day_start or end_time > owner.day_end:
                plan.add_unscheduled(t, "outside available hours")
            else:
                in_window_fixed.append(t)
        accepted_fixed = in_window_fixed

        # --- interleave flexible tasks into the gaps around fixed tasks ---
        cursor = owner.day_start
        flexible_queue = list(flexible_tasks)

        def fill_until(end_limit: time) -> None:
            nonlocal cursor, flexible_queue
            still_pending = []
            for task in flexible_queue:
                start_dt = datetime.combine(target_date, cursor)
                end_dt = start_dt + timedelta(minutes=task.duration_minutes)
                if end_dt.time() <= end_limit:
                    plan.add_item(
                        ScheduledTask(task, cursor, end_dt.time(), "Fit into available time")
                    )
                    cursor = end_dt.time()
                else:
                    still_pending.append(task)
            flexible_queue = still_pending

        for fixed_task in accepted_fixed:
            fill_until(fixed_task.preferred_time)
            start_time = fixed_task.preferred_time
            end_time = fixed_task.get_end_time(start_time)
            plan.add_item(ScheduledTask(fixed_task, start_time, end_time, "Fixed-time task"))
            cursor = end_time

        fill_until(owner.day_end)

        for task in flexible_queue:
            plan.add_unscheduled(task, "not enough time remaining in the day")

        return plan