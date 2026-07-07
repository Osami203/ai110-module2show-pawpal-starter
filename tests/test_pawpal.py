from datetime import date, time, timedelta

import pytest

from pawpal_system import (
    Appointment,
    Feeding,
    Medication,
    Owner,
    Pet,
    Priority,
    Recurrence,
    Scheduler,
    Walk,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def owner():
    return Owner(name="Jordan", day_start=time(7, 0), day_end=time(20, 0))


@pytest.fixture
def pet(owner):
    p = Pet(name="Mochi", species="dog")
    owner.add_pet(p)
    return p


# ---------------------------------------------------------------------------
# Task basics
# ---------------------------------------------------------------------------

def test_task_requires_positive_duration():
    with pytest.raises(ValueError):
        Walk("Bad walk", duration_minutes=0)


def test_appointment_requires_preferred_time():
    with pytest.raises(ValueError):
        Appointment("Vet visit", duration_minutes=30)


def test_medication_defaults_to_high_priority():
    med = Medication("Pill", duration_minutes=5, preferred_time=time(9, 0))
    assert med.priority == Priority.HIGH


def test_flexible_task_has_no_fixed_time():
    walk = Walk("Walk", duration_minutes=20)
    assert not walk.is_fixed_time


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

def test_sort_tasks_orders_by_priority_then_duration():
    low_long = Walk("Long low", duration_minutes=60, priority=Priority.LOW)
    high_short = Feeding("Short high", duration_minutes=5, priority=Priority.HIGH)
    high_long = Walk("Long high", duration_minutes=30, priority=Priority.HIGH)
    medium = Walk("Medium", duration_minutes=15, priority=Priority.MEDIUM)

    result = Scheduler.sort_tasks([low_long, high_long, medium, high_short])

    assert result == [high_short, high_long, medium, low_long]


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def test_detect_conflicts_finds_overlapping_fixed_tasks():
    a = Appointment("Vet", duration_minutes=45, preferred_time=time(14, 0))
    b = Appointment("Grooming", duration_minutes=30, preferred_time=time(14, 15))
    c = Appointment("Later thing", duration_minutes=15, preferred_time=time(16, 0))

    conflicts = Scheduler.detect_conflicts([a, b, c])

    assert len(conflicts) == 1
    assert {a, b} == set(conflicts[0])


def test_flexible_tasks_never_conflict():
    a = Walk("Walk 1", duration_minutes=20)
    b = Walk("Walk 2", duration_minutes=20)
    assert Scheduler.detect_conflicts([a, b]) == []


def test_conflicts_with_is_symmetric():
    a = Appointment("A", duration_minutes=30, preferred_time=time(10, 0))
    b = Appointment("B", duration_minutes=30, preferred_time=time(10, 15))
    assert a.conflicts_with(b) == b.conflicts_with(a) == True


def test_adjacent_tasks_do_not_conflict():
    a = Appointment("A", duration_minutes=30, preferred_time=time(10, 0))
    b = Appointment("B", duration_minutes=30, preferred_time=time(10, 30))
    assert not a.conflicts_with(b)


# ---------------------------------------------------------------------------
# Recurring tasks
# ---------------------------------------------------------------------------

def test_daily_task_is_due_every_day():
    task = Feeding("Breakfast", duration_minutes=10, recurrence=Recurrence.DAILY)
    monday = date(2026, 7, 6)
    assert task.is_due_on(monday)
    assert task.is_due_on(monday + timedelta(days=3))


def test_weekly_task_is_due_only_on_its_day():
    monday = date(2026, 7, 6)  # a Monday
    tuesday = monday + timedelta(days=1)
    task = Appointment(
        "Weekly grooming", duration_minutes=30, preferred_time=time(10, 0),
        recurrence=Recurrence.WEEKLY, day_of_week=0,  # Monday
    )
    assert task.is_due_on(monday)
    assert not task.is_due_on(tuesday)


def test_expand_recurring_filters_to_due_tasks(pet):
    monday = date(2026, 7, 6)
    daily_task = pet.add_task(Feeding("Breakfast", duration_minutes=10, recurrence=Recurrence.DAILY))
    weekly_wrong_day = pet.add_task(
        Appointment("Groom", duration_minutes=30, preferred_time=time(9, 0),
                    recurrence=Recurrence.WEEKLY, day_of_week=2)  # Wednesday
    )

    due_today = Scheduler.expand_recurring(pet.tasks, monday)

    assert daily_task in due_today
    assert weekly_wrong_day not in due_today


# ---------------------------------------------------------------------------
# Full plan building
# ---------------------------------------------------------------------------

def test_build_daily_plan_schedules_flexible_tasks_around_fixed_ones(owner, pet):
    pet.add_task(Walk("Morning walk", duration_minutes=30, priority=Priority.HIGH))
    pet.add_task(Medication("Pill", duration_minutes=5, preferred_time=time(8, 0)))

    plan = Scheduler.build_daily_plan(pet, date(2026, 7, 6), owner)

    titles_in_order = [item.task.title for item in plan.scheduled_items]
    assert titles_in_order == ["Morning walk", "Pill"]
    assert plan.unscheduled_tasks == []


def test_build_daily_plan_resolves_conflict_by_priority(owner, pet):
    high = pet.add_task(Appointment("Vet", duration_minutes=45, preferred_time=time(14, 0),
                                     priority=Priority.HIGH))
    low = pet.add_task(Appointment("Grooming", duration_minutes=30, preferred_time=time(14, 15),
                                    priority=Priority.MEDIUM))

    plan = Scheduler.build_daily_plan(pet, date(2026, 7, 6), owner)

    scheduled_titles = [item.task.title for item in plan.scheduled_items]
    unscheduled_titles = [t.title for t, _ in plan.unscheduled_tasks]
    assert high.title in scheduled_titles
    assert low.title in unscheduled_titles


def test_build_daily_plan_drops_fixed_task_outside_available_hours(owner, pet):
    pet.add_task(Appointment("Late night vet", duration_minutes=30, preferred_time=time(22, 0)))

    plan = Scheduler.build_daily_plan(pet, date(2026, 7, 6), owner)

    assert plan.scheduled_items == []
    assert plan.unscheduled_tasks[0][1] == "outside available hours"


def test_build_daily_plan_leaves_overflow_tasks_unscheduled():
    tight_owner = Owner(name="Busy", day_start=time(9, 0), day_end=time(9, 20))
    pet = Pet(name="Rex", species="dog", owner=tight_owner)
    tight_owner.add_pet(pet)
    pet.add_task(Walk("Long walk", duration_minutes=60, priority=Priority.HIGH))

    plan = Scheduler.build_daily_plan(pet, date(2026, 7, 6), tight_owner)

    assert plan.scheduled_items == []
    assert plan.unscheduled_tasks[0][1] == "not enough time remaining in the day"


def test_build_daily_plan_raises_without_owner():
    pet = Pet(name="Rex", species="dog")
    pet.add_task(Walk("Walk", duration_minutes=20))
    with pytest.raises(ValueError):
        Scheduler.build_daily_plan(pet, date(2026, 7, 6))