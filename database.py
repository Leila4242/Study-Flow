"""
database.py
Handles the PostgreSQL connection and schema creation for Study Planner.
Uses plain psycopg2 (no ORM) with parameterized queries only.

Reads the connection string from the DATABASE_URL environment variable.
On Render: Dashboard -> your Postgres instance -> copy the "Internal
Database URL" (if your web service is in the same region) and set it
as DATABASE_URL in your web service's Environment settings.

Locally: set DATABASE_URL to the "External Database URL" Render gives
you, or point it at a local Postgres instance
(e.g. postgresql://user:password@localhost:5432/study_planner).
"""

import os
from datetime import date

import psycopg2
import psycopg2.extras


DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """
    Opens a new connection to the Postgres database.
    Rows are returned as dict-like objects (RealDictRow) so columns
    can be accessed by name, e.g. row["email"] - same usage as before.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it in Render (or your local .env) before starting the app."
        )
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


# ==========================================================================
# Small internal helpers so every function below stays short.
# Each one opens a connection, runs one statement, and closes the
# connection - mirroring the original sqlite3 file's style.
# ==========================================================================

def _stringify_dates(row):
    """
    Postgres returns DATE/TIMESTAMP columns as Python date/datetime
    objects, but the original SQLite version of this app always dealt
    with plain 'YYYY-MM-DD' strings (e.g. app.py calls
    datetime.strptime(task["deadline"], "%Y-%m-%d")). Converting here
    keeps every function's return shape identical to before, so app.py
    needs no changes for date handling.
    """
    if row is None:
        return None
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return row


def _fetchone(sql, params=()):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        conn.commit()
        return _stringify_dates(row)
    finally:
        conn.close()


def _fetchall(sql, params=()):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.commit()
        return [_stringify_dates(row) for row in rows]
    finally:
        conn.close()


def _execute(sql, params=()):
    """Runs an INSERT/UPDATE/DELETE with no RETURNING clause. Returns affected row count."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _execute_returning_id(sql, params=()):
    """Runs an INSERT ... RETURNING id and returns the new id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        conn.close()


def init_db():
    """
    Creates all required tables. Safe to call every time the app starts
    (uses IF NOT EXISTS). Postgres enforces foreign keys by default,
    so there's no PRAGMA needed like in SQLite.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            fullname TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            teacher TEXT,
            color TEXT NOT NULL DEFAULT '#4F46E5',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            deadline DATE NOT NULL,
            priority TEXT NOT NULL CHECK (priority IN ('Low', 'Medium', 'High')),
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK (status IN ('Pending', 'In Progress', 'Completed')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            exam_date DATE NOT NULL,
            location TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            study_date DATE NOT NULL,
            duration INTEGER NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


# ==========================================================================
# User data-access helpers
# All queries are parameterized to prevent SQL injection.
# ==========================================================================

def create_user(fullname, email, hashed_password):
    """
    Inserts a new user. Returns the new user's id.
    Raises psycopg2.IntegrityError if the email already exists (UNIQUE constraint).
    """
    return _execute_returning_id(
        "INSERT INTO users (fullname, email, password) VALUES (%s, %s, %s) RETURNING id",
        (fullname, email, hashed_password),
    )


def get_user_by_email(email):
    """Returns a single user row matching the email, or None."""
    return _fetchone("SELECT * FROM users WHERE email = %s", (email,))


def get_user_by_id(user_id):
    """Returns a single user row matching the id, or None."""
    return _fetchone("SELECT * FROM users WHERE id = %s", (user_id,))


def update_user_profile(user_id, fullname, email):
    """
    Updates a user's fullname/email. Returns True on success, False if
    the email is already taken by a *different* user (UNIQUE constraint).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET fullname = %s, email = %s WHERE id = %s",
                (fullname, email, user_id),
            )
            conn.commit()
            return True
        except psycopg2.IntegrityError:
            conn.rollback()
            return False
    finally:
        conn.close()


def update_user_password(user_id, hashed_password):
    """Updates a user's password hash."""
    _execute(
        "UPDATE users SET password = %s WHERE id = %s",
        (hashed_password, user_id),
    )


# ==========================================================================
# Subject data-access helpers
# Every function is scoped by user_id so one student can never
# read, edit, or delete another student's subjects.
# ==========================================================================

def create_subject(user_id, name, teacher, color):
    """Inserts a new subject for a user. Returns the new subject's id."""
    return _execute_returning_id(
        "INSERT INTO subjects (user_id, name, teacher, color) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, name, teacher, color),
    )


def get_subjects_by_user(user_id):
    """
    Returns all subjects belonging to a user, ordered alphabetically,
    along with a live count of how many tasks each subject has.
    """
    return _fetchall(
        """
        SELECT
            subjects.*,
            COUNT(tasks.id) AS task_count
        FROM subjects
        LEFT JOIN tasks ON tasks.subject_id = subjects.id
        WHERE subjects.user_id = %s
        GROUP BY subjects.id
        ORDER BY LOWER(subjects.name) ASC
        """,
        (user_id,),
    )


def get_subject_by_id(subject_id, user_id):
    """
    Returns a single subject, but only if it belongs to the given user.
    Returns None if it doesn't exist or belongs to someone else.
    """
    return _fetchone(
        "SELECT * FROM subjects WHERE id = %s AND user_id = %s",
        (subject_id, user_id),
    )


def update_subject(subject_id, user_id, name, teacher, color):
    """
    Updates a subject, scoped to user_id.
    Returns True if a row was actually updated, False otherwise
    (e.g. the subject doesn't belong to this user).
    """
    rowcount = _execute(
        """
        UPDATE subjects
        SET name = %s, teacher = %s, color = %s
        WHERE id = %s AND user_id = %s
        """,
        (name, teacher, color, subject_id, user_id),
    )
    return rowcount > 0


def delete_subject(subject_id, user_id):
    """
    Deletes a subject, scoped to user_id.
    Cascades to its tasks/exams/study_sessions via ON DELETE CASCADE.
    Returns True if a row was actually deleted.
    """
    rowcount = _execute(
        "DELETE FROM subjects WHERE id = %s AND user_id = %s",
        (subject_id, user_id),
    )
    return rowcount > 0


# ==========================================================================
# Task (Assignment) data-access helpers
# Tasks don't store user_id directly - ownership is verified by joining
# through the parent subject, so every function here takes user_id
# and checks subjects.user_id in the WHERE/JOIN clause.
# ==========================================================================

def create_task(subject_id, user_id, title, description, deadline, priority, status):
    """
    Inserts a new task under a subject, but only if that subject
    actually belongs to user_id. Returns the new task's id, or None
    if the subject doesn't belong to this user.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM subjects WHERE id = %s AND user_id = %s",
            (subject_id, user_id),
        )
        owns_subject = cursor.fetchone()

        if owns_subject is None:
            conn.commit()
            return None

        cursor.execute(
            """
            INSERT INTO tasks (subject_id, title, description, deadline, priority, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (subject_id, title, description, deadline, priority, status),
        )
        new_id = cursor.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        conn.close()


def get_tasks_by_user(user_id, search=None, status_filter=None, priority_filter=None):
    """
    Returns all tasks belonging to a user (via their subjects), ordered
    by deadline ascending so the most urgent assignments surface first.
    Includes the parent subject's name/color for display. Supports
    optional server-side search (title/description) and status/priority
    filtering.
    """
    query = """
        SELECT
            tasks.*,
            subjects.name AS subject_name,
            subjects.color AS subject_color
        FROM tasks
        JOIN subjects ON subjects.id = tasks.subject_id
        WHERE subjects.user_id = %s
    """
    params = [user_id]

    if search:
        query += " AND (tasks.title ILIKE %s OR tasks.description ILIKE %s)"
        like_term = f"%{search}%"
        params.extend([like_term, like_term])

    if status_filter and status_filter != "All":
        query += " AND tasks.status = %s"
        params.append(status_filter)

    if priority_filter and priority_filter != "All":
        query += " AND tasks.priority = %s"
        params.append(priority_filter)

    query += " ORDER BY tasks.deadline ASC"

    return _fetchall(query, params)


def get_task_by_id(task_id, user_id):
    """
    Returns a single task (with its subject name/color joined in),
    but only if it belongs to a subject owned by user_id.
    """
    return _fetchone(
        """
        SELECT tasks.*, subjects.name AS subject_name, subjects.color AS subject_color
        FROM tasks
        JOIN subjects ON subjects.id = tasks.subject_id
        WHERE tasks.id = %s AND subjects.user_id = %s
        """,
        (task_id, user_id),
    )


def update_task(task_id, user_id, subject_id, title, description, deadline, priority, status):
    """
    Updates a task. Verifies both that the task belongs to user_id
    AND that the (possibly new) subject_id also belongs to user_id,
    so a task can never be reassigned to someone else's subject.
    Returns True if the update happened.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM subjects WHERE id = %s AND user_id = %s",
            (subject_id, user_id),
        )
        owns_subject = cursor.fetchone()

        if owns_subject is None:
            conn.commit()
            return False

        cursor.execute(
            """
            UPDATE tasks
            SET subject_id = %s, title = %s, description = %s, deadline = %s, priority = %s, status = %s
            WHERE id = %s AND subject_id IN (SELECT id FROM subjects WHERE user_id = %s)
            """,
            (subject_id, title, description, deadline, priority, status, task_id, user_id),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def delete_task(task_id, user_id):
    """
    Deletes a task, but only if it belongs to a subject owned by user_id.
    Returns True if a row was actually deleted.
    """
    rowcount = _execute(
        """
        DELETE FROM tasks
        WHERE id = %s AND subject_id IN (SELECT id FROM subjects WHERE user_id = %s)
        """,
        (task_id, user_id),
    )
    return rowcount > 0


def update_task_status(task_id, user_id, status):
    """
    Quick status-only update, used by the one-click status change
    control on the task cards (no need to resubmit the whole form).
    """
    rowcount = _execute(
        """
        UPDATE tasks
        SET status = %s
        WHERE id = %s AND subject_id IN (SELECT id FROM subjects WHERE user_id = %s)
        """,
        (status, task_id, user_id),
    )
    return rowcount > 0


# ==========================================================================
# Dashboard data-access helpers
# Everything here is read-only and scoped to a single user_id, feeding
# the widgets on the dashboard (stats, today's tasks, exams, activity,
# progress overview).
# ==========================================================================

def get_dashboard_stats(user_id):
    """
    Returns the headline numbers shown on the Statistics Cards:
    total subjects, total assignments, how many are due today,
    how many are overdue, how many are completed, and how many
    exams are still upcoming.
    """
    subject_count = _fetchone(
        "SELECT COUNT(*) AS c FROM subjects WHERE user_id = %s", (user_id,)
    )["c"]

    task_totals = _fetchone(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN tasks.status = 'Completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN tasks.status != 'Completed' AND tasks.deadline < %s THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN tasks.status != 'Completed' AND tasks.deadline = %s THEN 1 ELSE 0 END) AS due_today
        FROM tasks
        JOIN subjects ON subjects.id = tasks.subject_id
        WHERE subjects.user_id = %s
        """,
        (date.today().isoformat(), date.today().isoformat(), user_id),
    )

    upcoming_exam_count = _fetchone(
        """
        SELECT COUNT(*) AS c
        FROM exams
        JOIN subjects ON subjects.id = exams.subject_id
        WHERE subjects.user_id = %s AND exams.exam_date >= %s
        """,
        (user_id, date.today().isoformat()),
    )["c"]

    return {
        "subject_count": subject_count,
        "total_tasks": task_totals["total"] or 0,
        "completed_tasks": task_totals["completed"] or 0,
        "overdue_tasks": task_totals["overdue"] or 0,
        "due_today_tasks": task_totals["due_today"] or 0,
        "upcoming_exam_count": upcoming_exam_count,
    }


def get_today_tasks(user_id):
    """
    Returns all not-yet-completed tasks whose deadline is today,
    with the parent subject's name/color joined in, most urgent
    priority first.
    """
    return _fetchall(
        """
        SELECT
            tasks.*,
            subjects.name AS subject_name,
            subjects.color AS subject_color
        FROM tasks
        JOIN subjects ON subjects.id = tasks.subject_id
        WHERE subjects.user_id = %s
            AND tasks.deadline = %s
            AND tasks.status != 'Completed'
        ORDER BY
            CASE tasks.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
            LOWER(tasks.title) ASC
        """,
        (user_id, date.today().isoformat()),
    )


def get_upcoming_exams(user_id, limit=5):
    """
    Returns the next `limit` upcoming exams (today or later), soonest
    first, with the parent subject's name/color joined in.
    """
    return _fetchall(
        """
        SELECT
            exams.*,
            subjects.name AS subject_name,
            subjects.color AS subject_color
        FROM exams
        JOIN subjects ON subjects.id = exams.subject_id
        WHERE subjects.user_id = %s AND exams.exam_date >= %s
        ORDER BY exams.exam_date ASC
        LIMIT %s
        """,
        (user_id, date.today().isoformat(), limit),
    )


# ==========================================================================
# Exam data-access helpers
# Same ownership pattern as tasks: exams don't store user_id directly,
# ownership is verified by joining through / checking the parent subject.
# ==========================================================================

def create_exam(subject_id, user_id, title, exam_date, location, notes):
    """
    Inserts a new exam under a subject, but only if that subject
    actually belongs to user_id. Returns the new exam's id, or None
    if the subject doesn't belong to this user.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM subjects WHERE id = %s AND user_id = %s",
            (subject_id, user_id),
        )
        owns_subject = cursor.fetchone()

        if owns_subject is None:
            conn.commit()
            return None

        cursor.execute(
            """
            INSERT INTO exams (subject_id, title, exam_date, location, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (subject_id, title, exam_date, location, notes),
        )
        new_id = cursor.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        conn.close()


def get_exams_by_user(user_id):
    """
    Returns every exam belonging to a user (via their subjects), soonest
    first, with the parent subject's name/color joined in. Used by the
    full Exams page (both upcoming and past sections).
    """
    return _fetchall(
        """
        SELECT
            exams.*,
            subjects.name AS subject_name,
            subjects.color AS subject_color
        FROM exams
        JOIN subjects ON subjects.id = exams.subject_id
        WHERE subjects.user_id = %s
        ORDER BY exams.exam_date ASC
        """,
        (user_id,),
    )


def get_exam_by_id(exam_id, user_id):
    """
    Returns a single exam (with its subject name/color joined in),
    but only if it belongs to a subject owned by user_id.
    """
    return _fetchone(
        """
        SELECT exams.*, subjects.name AS subject_name, subjects.color AS subject_color
        FROM exams
        JOIN subjects ON subjects.id = exams.subject_id
        WHERE exams.id = %s AND subjects.user_id = %s
        """,
        (exam_id, user_id),
    )


def update_exam(exam_id, user_id, subject_id, title, exam_date, location, notes):
    """
    Updates an exam. Verifies both that the exam belongs to user_id
    AND that the (possibly new) subject_id also belongs to user_id,
    so an exam can never be reassigned to someone else's subject.
    Returns True if the update happened.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM subjects WHERE id = %s AND user_id = %s",
            (subject_id, user_id),
        )
        owns_subject = cursor.fetchone()

        if owns_subject is None:
            conn.commit()
            return False

        cursor.execute(
            """
            UPDATE exams
            SET subject_id = %s, title = %s, exam_date = %s, location = %s, notes = %s
            WHERE id = %s AND subject_id IN (SELECT id FROM subjects WHERE user_id = %s)
            """,
            (subject_id, title, exam_date, location, notes, exam_id, user_id),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def delete_exam(exam_id, user_id):
    """
    Deletes an exam, but only if it belongs to a subject owned by user_id.
    Returns True if a row was actually deleted.
    """
    rowcount = _execute(
        """
        DELETE FROM exams
        WHERE id = %s AND subject_id IN (SELECT id FROM subjects WHERE user_id = %s)
        """,
        (exam_id, user_id),
    )
    return rowcount > 0


def get_subject_progress(user_id):
    """
    Returns each subject with its task completion breakdown, used by
    the Progress Overview widget (per-subject progress bars).
    Subjects with zero tasks are included with percent=0.
    """
    rows = _fetchall(
        """
        SELECT
            subjects.id, subjects.name, subjects.color,
            COUNT(tasks.id) AS total_tasks,
            SUM(CASE WHEN tasks.status = 'Completed' THEN 1 ELSE 0 END) AS completed_tasks
        FROM subjects
        LEFT JOIN tasks ON tasks.subject_id = subjects.id
        WHERE subjects.user_id = %s
        GROUP BY subjects.id
        ORDER BY LOWER(subjects.name) ASC
        """,
        (user_id,),
    )

    progress = []
    for row in rows:
        total = row["total_tasks"] or 0
        completed = row["completed_tasks"] or 0
        percent = round((completed / total) * 100) if total else 0
        progress.append({
            "id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "total_tasks": total,
            "completed_tasks": completed,
            "percent": percent,
        })
    return progress


def get_recent_activity(user_id, limit=8):
    """
    Builds a unified 'Recent Activity' feed by merging subject creations
    and task creations (there's no separate activity-log table), sorted
    newest first. Each entry is a plain dict ready for the template.
    """
    subject_rows = _fetchall(
        """
        SELECT name, color, created_at
        FROM subjects
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    )

    task_rows = _fetchall(
        """
        SELECT tasks.title, subjects.name AS subject_name, subjects.color AS subject_color,
               tasks.created_at
        FROM tasks
        JOIN subjects ON subjects.id = tasks.subject_id
        WHERE subjects.user_id = %s
        ORDER BY tasks.created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    )

    activity = []
    for row in subject_rows:
        activity.append({
            "icon": "fa-layer-group",
            "color": row["color"],
            "text": f"Added subject \u201c{row['name']}\u201d",
            "created_at": row["created_at"],
        })
    for row in task_rows:
        activity.append({
            "icon": "fa-list-check",
            "color": row["subject_color"],
            "text": f"Added assignment \u201c{row['title']}\u201d to {row['subject_name']}",
            "created_at": row["created_at"],
        })

    activity.sort(key=lambda item: item["created_at"], reverse=True)
    return activity[:limit]


# ==========================================================================
# Calendar data-access helpers
# ==========================================================================

def get_calendar_events(user_id, start_date, end_date):
    """
    Returns a dict keyed by ISO date string ('YYYY-MM-DD') -> list of
    event dicts, built from every assignment deadline, exam date, and
    study session date that falls within [start_date, end_date]
    (inclusive) for this user. Each event dict has: type ('task' |
    'exam' | 'study'), icon, title, meta - ready for the Calendar page.
    """
    task_rows = _fetchall(
        """
        SELECT tasks.title, tasks.deadline AS event_date, tasks.priority,
               subjects.name AS subject_name
        FROM tasks
        JOIN subjects ON subjects.id = tasks.subject_id
        WHERE subjects.user_id = %s AND tasks.deadline BETWEEN %s AND %s
        """,
        (user_id, start_date, end_date),
    )

    exam_rows = _fetchall(
        """
        SELECT exams.title, exams.exam_date AS event_date, exams.location,
               subjects.name AS subject_name
        FROM exams
        JOIN subjects ON subjects.id = exams.subject_id
        WHERE subjects.user_id = %s AND exams.exam_date BETWEEN %s AND %s
        """,
        (user_id, start_date, end_date),
    )

    study_rows = _fetchall(
        """
        SELECT study_sessions.study_date AS event_date, study_sessions.duration,
               subjects.name AS subject_name
        FROM study_sessions
        JOIN subjects ON subjects.id = study_sessions.subject_id
        WHERE subjects.user_id = %s AND study_sessions.study_date BETWEEN %s AND %s
        """,
        (user_id, start_date, end_date),
    )

    events_by_date = {}

    for row in task_rows:
        event_date = row["event_date"]
        events_by_date.setdefault(event_date, []).append({
            "type": "task",
            "icon": "fa-list-check",
            "title": row["title"],
            "meta": f"{row['subject_name']} \u00b7 {row['priority']} priority",
        })

    for row in exam_rows:
        event_date = row["event_date"]
        meta = row["subject_name"]
        if row["location"]:
            meta += f" \u00b7 {row['location']}"
        events_by_date.setdefault(event_date, []).append({
            "type": "exam",
            "icon": "fa-file-pen",
            "title": row["title"],
            "meta": meta,
        })

    for row in study_rows:
        event_date = row["event_date"]
        hours, minutes = divmod(row["duration"], 60)
        if hours and minutes:
            duration_display = f"{hours}h {minutes}m"
        elif hours:
            duration_display = f"{hours}h"
        else:
            duration_display = f"{minutes}m"
        events_by_date.setdefault(event_date, []).append({
            "type": "study",
            "icon": "fa-stopwatch",
            "title": f"{row['subject_name']} study session",
            "meta": duration_display,
        })

    return events_by_date
