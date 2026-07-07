"""
CLI demo for PawPal+.

Run this to verify the backend logic works before connecting it to
the Streamlit UI (app.py). This is intentionally plain-text / no
dependencies beyond the standard library plus pawpal_system.

    python demo.py
"""

from datetime import date, time

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


def build_sample_data():
    owner = Owner(name="Jordan", day_start=time(7, 0), day_end=time(20, 0))
    pet = Pet(name="Mochi", species="dog", breed="Golden Retriever")
    owner.add_pet(pet)

    pet.add_task(Walk("Morning walk", duration_minutes=30, priority=Priority.HIGH,
                       recurrence=Recurrence.DAILY))
    pet.add_task(Feeding("Breakfast", duration_minutes=10, priority=Priority.HIGH,
                          recurrence=Recurrence.DAILY))
    pet.add_task(Medication("Heartworm pill", duration_minutes=5,
                             preferred_time=time(8, 0), recurrence=Recurrence.DAILY))
    pet.add_task(Appointment("Vet checkup", duration_minutes=45,
                              preferred_time=time(14, 0)))
    pet.add_task(Walk("Evening walk", duration_minutes=30, priority=Priority.MEDIUM,
                       recurrence=Recurrence.DAILY))
    pet.add_task(Feeding("Dinner", duration_minutes=10, priority=Priority.HIGH,
                          recurrence=Recurrence.DAILY))
    pet.add_task(Walk("Extra enrichment play", duration_minutes=60, priority=Priority.LOW,
                       recurrence=Recurrence.DAILY))
    # A deliberately conflicting appointment to show conflict handling:
    pet.add_task(Appointment("Grooming", duration_minutes=30, preferred_time=time(14, 15),
                              priority=Priority.MEDIUM))

    return owner, pet


def main():
    owner, pet = build_sample_data()
    today = date.today()

    print("=== Sorted tasks (priority desc, duration asc) ===")
    for t in Scheduler.sort_tasks(pet.tasks):
        print(" ", t)

    print("\n=== Conflicts detected ===")
    conflicts = Scheduler.detect_conflicts(pet.tasks)
    if not conflicts:
        print("  None")
    for a, b in conflicts:
        print(f"  '{a.title}' overlaps '{b.title}'")

    print("\n=== Daily plan ===")
    plan = Scheduler.build_daily_plan(pet, today, owner)
    print(plan.summary())


if __name__ == "__main__":
    main()