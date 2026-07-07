from datetime import date, time

import streamlit as st

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

st.set_page_config(page_title="PawPal+", page_icon=":dog:", layout="centered")

st.title("PawPal+")
st.caption("A pet care planning assistant")

TASK_CLASSES = {
    "Walk": Walk,
    "Feeding": Feeding,
    "Medication": Medication,
    "Appointment": Appointment,
}

if "tasks" not in st.session_state:
    st.session_state.tasks = []  # list of Task objects

with st.expander("Owner & pet info", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        owner_name = st.text_input("Owner name", value="Jordan")
        day_start = st.time_input("Day starts at", value=time(7, 0))
    with col2:
        pet_name = st.text_input("Pet name", value="Mochi")
        day_end = st.time_input("Day ends at", value=time(20, 0))
    species = st.selectbox("Species", ["dog", "cat", "other"])

st.divider()

st.subheader("Tasks")

with st.form("add_task_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        task_title = st.text_input("Task title", value="Morning walk")
        task_type = st.selectbox("Type", list(TASK_CLASSES.keys()))
    with col2:
        duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
        priority_label = st.selectbox("Priority", ["low", "medium", "high"], index=2)
    with col3:
        has_fixed_time = st.checkbox("Has a fixed time?", value=(task_type in ("Medication", "Appointment")))
        fixed_time = st.time_input("At time", value=time(9, 0), disabled=not has_fixed_time)
        recurrence_label = st.selectbox("Recurrence", ["none", "daily", "weekly"])

    submitted = st.form_submit_button("Add task")

    if submitted:
        task_cls = TASK_CLASSES[task_type]
        kwargs = dict(
            title=task_title,
            duration_minutes=int(duration),
            priority=Priority[priority_label.upper()],
            recurrence=Recurrence(recurrence_label),
        )
        if has_fixed_time:
            kwargs["preferred_time"] = fixed_time

        try:
            new_task = task_cls(**kwargs)
            st.session_state.tasks.append(new_task)
            st.success(f"Added '{task_title}'")
        except ValueError as e:
            st.error(str(e))

if st.session_state.tasks:
    st.write("Current tasks:")
    st.table(
        [
            {
                "title": t.title,
                "type": t.__class__.__name__,
                "duration (min)": t.duration_minutes,
                "priority": t.priority.name.lower(),
                "time": t.preferred_time.strftime("%H:%M") if t.preferred_time else "flexible",
                "recurrence": t.recurrence.value,
            }
            for t in st.session_state.tasks
        ]
    )
    if st.button("Clear all tasks"):
        st.session_state.tasks = []
        st.rerun()
else:
    st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build schedule")
plan_date = st.date_input("Plan for date", value=date.today())

if st.button("Generate schedule", type="primary"):
    if not st.session_state.tasks:
        st.warning("Add at least one task first.")
    else:
        owner = Owner(name=owner_name, day_start=day_start, day_end=day_end)
        pet = Pet(name=pet_name, species=species)
        owner.add_pet(pet)
        for t in st.session_state.tasks:
            pet.add_task(t)

        plan = Scheduler.build_daily_plan(pet, plan_date, owner)

        st.markdown(f"### Plan for {pet.name} on {plan_date.isoformat()}")

        if plan.scheduled_items:
            for item in plan.scheduled_items:
                st.write(
                    f"**{item.start_time.strftime('%H:%M')}** -- {item.task.title} "
                    f"({item.task.duration_minutes} min) "
                    f"· priority: {item.task.priority.name.lower()} "
                    f"· _{item.reason}_"
                )
        else:
            st.info("Nothing could be scheduled.")

        if plan.unscheduled_tasks:
            st.markdown("#### Could not fit")
            for task, reason in plan.unscheduled_tasks:
                st.write(f"- **{task.title}**: {reason}")

        conflicts = Scheduler.detect_conflicts(st.session_state.tasks)
        if conflicts:
            st.markdown("#### Conflicts detected")
            for a, b in conflicts:
                st.write(f"- '{a.title}' overlaps '{b.title}'")