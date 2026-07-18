"""
app.py
Study Planner - Flask entry point.

Step 2 scope:
- Full authentication system: register, login, logout
- Passwords hashed with Werkzeug
- Flask session used to track the logged-in user
- login_required decorator protects dashboard routes
- Server-side validation + flash messages for every auth form
"""

import re
import psycopg2
from calendar import Calendar, monthrange
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import date, datetime, timedelta

from database import (
    init_db, create_user, get_user_by_email, get_user_by_id,
    update_user_profile, update_user_password,
    create_subject, get_subjects_by_user, get_subject_by_id,
    update_subject, delete_subject,
    create_task, get_tasks_by_user, get_task_by_id,
    update_task, delete_task, update_task_status,
    create_exam, get_exams_by_user, get_exam_by_id,
    update_exam, delete_exam,
    get_dashboard_stats, get_today_tasks, get_upcoming_exams,
    get_subject_progress, get_recent_activity, get_calendar_events,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-this-in-production"

# Create tables on startup if they don't exist yet
init_db()

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HEX_COLOR_REGEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Palette offered as quick-pick swatches on the Add/Edit Subject forms
SUBJECT_COLOR_PALETTE = [
    "#4F46E5", "#6366F1", "#10B981", "#F59E0B",
    "#EF4444", "#EC4899", "#06B6D4", "#8B5CF6",
]

TASK_PRIORITIES = ["Low", "Medium", "High"]
TASK_STATUSES = ["Pending", "In Progress", "Completed"]
CALENDAR_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def format_friendly_date(d):
    """
    Formats a date as "Jan 5, 2026" without relying on the %-d strftime
    specifier, which only exists on Linux/Mac and crashes on Windows.
    """
    return f"{d.strftime('%b')} {d.day}, {d.year}"


# ==========================================================================
# Auth helpers
# ==========================================================================

def login_required(view_func):
    """
    Decorator that redirects unauthenticated users to the login page.
    Wrap any dashboard-only route with this.
    """
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


@app.context_processor
def inject_current_user():
    """
    Makes `current_user` available in every template automatically,
    so base.html can show the real name/initials instead of placeholders.
    """
    user = None
    if "user_id" in session:
        user = get_user_by_id(session["user_id"])
    return {"current_user": user}


# ==========================================================================
# Routes
# ==========================================================================

@app.route("/")
def index():
    """Root route: send logged-in users to the dashboard and everyone else to the login page."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Already logged in? No need to register again.
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []

        if not fullname:
            errors.append("Full name is required.")

        if not email:
            errors.append("Email is required.")
        elif not EMAIL_REGEX.match(email):
            errors.append("Please enter a valid email address.")

        if not password:
            errors.append("Password is required.")
        elif len(password) < 6:
            errors.append("Password must be at least 6 characters long.")

        if password != confirm_password:
            errors.append("Passwords do not match.")

        # Only hit the database if the basic fields are valid so far
        if not errors and get_user_by_email(email) is not None:
            errors.append("An account with this email already exists.")

        if errors:
            for error in errors:
                flash(error, "error")
            # Re-populate the form so the user doesn't have to retype everything
            return render_template(
                "register.html",
                fullname=fullname,
                email=email,
            )

        hashed_password = generate_password_hash(password)

        try:
            create_user(fullname, email, hashed_password)
        except psycopg2.IntegrityError:
            flash("An account with this email already exists.", "error")
            return render_template("register.html", fullname=fullname, email=email)

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Already logged in? Skip straight to the dashboard.
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        errors = []
        if not email:
            errors.append("Email is required.")
        if not password:
            errors.append("Password is required.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("login.html", email=email)

        user = get_user_by_email(email)

        if user is None or not check_password_hash(user["password"], password):
            flash("Incorrect email or password.", "error")
            return render_template("login.html", email=email)

        session.clear()
        session["user_id"] = user["id"]
        session["fullname"] = user["fullname"]

        flash(f"Welcome back, {user['fullname']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]

    return render_template(
        "dashboard.html",
        stats=get_dashboard_stats(user_id),
        today_tasks=get_today_tasks(user_id),
        upcoming_exams=get_upcoming_exams(user_id),
        subject_progress=get_subject_progress(user_id),
        recent_activity=get_recent_activity(user_id),
        subjects=get_subjects_by_user(user_id),
        priorities=TASK_PRIORITIES,
        today=date.today().isoformat(),
    )


@app.route("/dashboard/quick-add-task", methods=["POST"])
@login_required
def quick_add_task():
    """
    Lightweight assignment creation from the dashboard's Quick Add Task
    widget. Reuses the same validation rules as the full Add Assignment
    form but always redirects back to the dashboard, success or error.
    """
    subject_id = request.form.get("subject_id", "")
    title = request.form.get("title", "").strip()
    deadline_raw = request.form.get("deadline", "").strip()
    priority = request.form.get("priority", "")

    errors = []

    if not subject_id:
        errors.append("Please choose a subject.")

    if not title:
        errors.append("Title is required.")
    elif len(title) > 120:
        errors.append("Title must be 120 characters or fewer.")

    deadline, deadline_error = parse_deadline(deadline_raw)
    if deadline_error:
        errors.append(deadline_error)

    if priority not in TASK_PRIORITIES:
        errors.append("Please choose a valid priority.")

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("dashboard"))

    new_id = create_task(
        int(subject_id), session["user_id"],
        title, "", deadline, priority, "Pending",
    )

    if new_id is None:
        flash("That subject isn't yours - please pick again.", "error")
    else:
        flash("Assignment added successfully.", "success")

    return redirect(url_for("dashboard"))


# ==========================================================================
# Subjects (CRUD)
# ==========================================================================

@app.route("/subjects")
@login_required
def subjects():
    all_subjects = get_subjects_by_user(session["user_id"])
    return render_template("subjects.html", subjects=all_subjects)


@app.route("/subjects/add", methods=["GET", "POST"])
@login_required
def add_subject():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        teacher = request.form.get("teacher", "").strip()
        color = request.form.get("color", "").strip()

        errors = []

        if not name:
            errors.append("Subject name is required.")
        elif len(name) > 80:
            errors.append("Subject name must be 80 characters or fewer.")

        if not color:
            color = SUBJECT_COLOR_PALETTE[0]
        elif not HEX_COLOR_REGEX.match(color):
            errors.append("Please choose a valid color.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_subject.html",
                name=name, teacher=teacher, color=color,
                palette=SUBJECT_COLOR_PALETTE,
            )

        create_subject(session["user_id"], name, teacher, color)
        flash("Subject added successfully.", "success")
        return redirect(url_for("subjects"))

    return render_template(
        "add_subject.html",
        color=SUBJECT_COLOR_PALETTE[0],
        palette=SUBJECT_COLOR_PALETTE,
    )


@app.route("/subjects/edit/<int:subject_id>", methods=["GET", "POST"])
@login_required
def edit_subject(subject_id):
    subject = get_subject_by_id(subject_id, session["user_id"])
    if subject is None:
        flash("That subject doesn't exist or isn't yours to edit.", "error")
        return redirect(url_for("subjects"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        teacher = request.form.get("teacher", "").strip()
        color = request.form.get("color", "").strip()

        errors = []

        if not name:
            errors.append("Subject name is required.")
        elif len(name) > 80:
            errors.append("Subject name must be 80 characters or fewer.")

        if not color:
            color = subject["color"]
        elif not HEX_COLOR_REGEX.match(color):
            errors.append("Please choose a valid color.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "edit_subject.html",
                subject=subject,
                name=name, teacher=teacher, color=color,
                palette=SUBJECT_COLOR_PALETTE,
            )

        update_subject(subject_id, session["user_id"], name, teacher, color)
        flash("Subject updated successfully.", "success")
        return redirect(url_for("subjects"))

    return render_template(
        "edit_subject.html",
        subject=subject,
        palette=SUBJECT_COLOR_PALETTE,
    )


@app.route("/subjects/delete/<int:subject_id>", methods=["POST"])
@login_required
def delete_subject_route(subject_id):
    deleted = delete_subject(subject_id, session["user_id"])
    if deleted:
        flash("Subject deleted.", "success")
    else:
        flash("That subject doesn't exist or isn't yours to delete.", "error")
    return redirect(url_for("subjects"))


# ==========================================================================
# Tasks / Assignments (CRUD + Search + Filter)
# ==========================================================================

def parse_deadline(raw_value):
    """
    Validates a deadline string is a real date in YYYY-MM-DD format
    and is not in the past. Returns (date_string, error_message).
    error_message is None when the deadline is valid.
    """
    if not raw_value:
        return None, "Deadline is required."

    try:
        parsed = datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        return None, "Please enter a valid date."

    if parsed < date.today():
        return None, "Deadline cannot be before today."

    return raw_value, None


def enrich_tasks_with_deadline_info(task_rows):
    """
    Converts task records into plain dicts and attaches:
    - deadline_display: a human-readable label ("Overdue by 2 days", "Due today", etc.)
    - deadline_status: a CSS class suffix (overdue / today / soon / upcoming / done)
    Completed tasks always get the neutral 'done' status regardless of date.
    """
    today = date.today()
    enriched = []

    for row in task_rows:
        task = dict(row)
        deadline_date = datetime.strptime(task["deadline"], "%Y-%m-%d").date()
        days_diff = (deadline_date - today).days

        if task["status"] == "Completed":
            task["deadline_status"] = "done"
            task["deadline_display"] = format_friendly_date(deadline_date)
        elif days_diff < 0:
            task["deadline_status"] = "overdue"
            overdue_days = abs(days_diff)
            task["deadline_display"] = f"Overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
        elif days_diff == 0:
            task["deadline_status"] = "today"
            task["deadline_display"] = "Due today"
        elif days_diff == 1:
            task["deadline_status"] = "soon"
            task["deadline_display"] = "Due tomorrow"
        elif days_diff <= 7:
            task["deadline_status"] = "soon"
            task["deadline_display"] = f"Due in {days_diff} days"
        else:
            task["deadline_status"] = "upcoming"
            task["deadline_display"] = format_friendly_date(deadline_date)

        enriched.append(task)

    return enriched


@app.route("/tasks")
@login_required
def tasks():
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "All")
    priority_filter = request.args.get("priority", "All")

    all_tasks = get_tasks_by_user(
        session["user_id"],
        search=search or None,
        status_filter=status_filter,
        priority_filter=priority_filter,
    )
    all_tasks = enrich_tasks_with_deadline_info(all_tasks)

    return render_template(
        "tasks.html",
        tasks=all_tasks,
        search=search,
        status_filter=status_filter,
        priority_filter=priority_filter,
        statuses=TASK_STATUSES,
        priorities=TASK_PRIORITIES,
        today=date.today().isoformat(),
    )


@app.route("/tasks/add", methods=["GET", "POST"])
@login_required
def add_task():
    user_subjects = get_subjects_by_user(session["user_id"])

    if request.method == "POST":
        subject_id = request.form.get("subject_id", "")
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline_raw = request.form.get("deadline", "").strip()
        priority = request.form.get("priority", "")
        status = request.form.get("status", "Pending")

        errors = []

        if not user_subjects:
            errors.append("Add a subject before creating an assignment.")

        if not subject_id:
            errors.append("Please choose a subject.")

        if not title:
            errors.append("Title is required.")
        elif len(title) > 120:
            errors.append("Title must be 120 characters or fewer.")

        deadline, deadline_error = parse_deadline(deadline_raw)
        if deadline_error:
            errors.append(deadline_error)

        if priority not in TASK_PRIORITIES:
            errors.append("Please choose a valid priority.")

        if status not in TASK_STATUSES:
            status = "Pending"

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_task.html",
                subjects=user_subjects,
                subject_id=subject_id, title=title, description=description,
                deadline=deadline_raw, priority=priority, status=status,
                priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
                today=date.today().isoformat(),
            )

        new_id = create_task(
            int(subject_id), session["user_id"],
            title, description, deadline, priority, status,
        )

        if new_id is None:
            flash("That subject isn't yours - please pick again.", "error")
            return render_template(
                "add_task.html",
                subjects=user_subjects,
                subject_id=subject_id, title=title, description=description,
                deadline=deadline_raw, priority=priority, status=status,
                priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
                today=date.today().isoformat(),
            )

        flash("Assignment added successfully.", "success")
        return redirect(url_for("tasks"))

    return render_template(
        "add_task.html",
        subjects=user_subjects,
        status="Pending",
        priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
        today=date.today().isoformat(),
    )


@app.route("/tasks/edit/<int:task_id>", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    task = get_task_by_id(task_id, session["user_id"])
    if task is None:
        flash("That assignment doesn't exist or isn't yours to edit.", "error")
        return redirect(url_for("tasks"))

    user_subjects = get_subjects_by_user(session["user_id"])

    if request.method == "POST":
        subject_id = request.form.get("subject_id", "")
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline_raw = request.form.get("deadline", "").strip()
        priority = request.form.get("priority", "")
        status = request.form.get("status", "")

        errors = []

        if not subject_id:
            errors.append("Please choose a subject.")

        if not title:
            errors.append("Title is required.")
        elif len(title) > 120:
            errors.append("Title must be 120 characters or fewer.")

        # Only enforce "not in the past" when the deadline is actually
        # changing - otherwise saving any other edit on an already-overdue
        # task would be impossible.
        if deadline_raw == task["deadline"]:
            deadline, deadline_error = deadline_raw, None
        else:
            deadline, deadline_error = parse_deadline(deadline_raw)
        if deadline_error:
            errors.append(deadline_error)

        if priority not in TASK_PRIORITIES:
            errors.append("Please choose a valid priority.")

        if status not in TASK_STATUSES:
            errors.append("Please choose a valid status.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "edit_task.html",
                task=task, subjects=user_subjects,
                subject_id=subject_id, title=title, description=description,
                deadline=deadline_raw, priority=priority, status=status,
                priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
                today=date.today().isoformat(),
            )

        updated = update_task(
            task_id, session["user_id"], int(subject_id),
            title, description, deadline, priority, status,
        )

        if not updated:
            flash("That subject isn't yours - please pick again.", "error")
            return render_template(
                "edit_task.html",
                task=task, subjects=user_subjects,
                subject_id=subject_id, title=title, description=description,
                deadline=deadline_raw, priority=priority, status=status,
                priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
                today=date.today().isoformat(),
            )

        flash("Assignment updated successfully.", "success")
        return redirect(url_for("tasks"))

    return render_template(
        "edit_task.html",
        task=task, subjects=user_subjects,
        priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
        today=date.today().isoformat(),
    )


@app.route("/tasks/delete/<int:task_id>", methods=["POST"])
@login_required
def delete_task_route(task_id):
    deleted = delete_task(task_id, session["user_id"])
    if deleted:
        flash("Assignment deleted.", "success")
    else:
        flash("That assignment doesn't exist or isn't yours to delete.", "error")
    return redirect(url_for("tasks"))


@app.route("/tasks/status/<int:task_id>", methods=["POST"])
@login_required
def update_task_status_route(task_id):
    """Quick one-click status change from the task card dropdown."""
    new_status = request.form.get("status", "")
    if new_status not in TASK_STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("tasks"))

    updated = update_task_status(task_id, session["user_id"], new_status)
    if updated:
        flash(f"Status updated to {new_status}.", "success")
    else:
        flash("That assignment doesn't exist or isn't yours to update.", "error")
    return redirect(url_for("tasks"))


# ==========================================================================
# Exams (CRUD + Countdown)
# ==========================================================================

def parse_exam_date(raw_value):
    """
    Validates an exam date string is a real date in YYYY-MM-DD format.
    Unlike task deadlines, past dates are allowed - an exam that already
    happened is still a legitimate record (notes, past location, etc.).
    Returns (date_string, error_message).
    """
    if not raw_value:
        return None, "Exam date is required."

    try:
        datetime.strptime(raw_value, "%Y-%m-%d")
    except ValueError:
        return None, "Please enter a valid date."

    return raw_value, None


def enrich_exams_with_countdown_info(exam_rows):
    """
    Converts exam records into plain dicts and attaches:
    - is_upcoming: True if the exam is today or in the future
    - countdown_status: a CSS class suffix (past / today / soon / upcoming)
    - countdown_display: a server-rendered fallback label, live-replaced
      by a ticking JS countdown on the Exams page for upcoming exams.
    """
    today = date.today()
    enriched = []

    for row in exam_rows:
        exam = dict(row)
        exam_date = datetime.strptime(exam["exam_date"], "%Y-%m-%d").date()
        days_diff = (exam_date - today).days

        exam["is_upcoming"] = days_diff >= 0

        if days_diff < 0:
            exam["countdown_status"] = "past"
            exam["countdown_display"] = format_friendly_date(exam_date)
        elif days_diff == 0:
            exam["countdown_status"] = "today"
            exam["countdown_display"] = "Today"
        elif days_diff == 1:
            exam["countdown_status"] = "soon"
            exam["countdown_display"] = "Tomorrow"
        elif days_diff <= 7:
            exam["countdown_status"] = "soon"
            exam["countdown_display"] = f"In {days_diff} days"
        else:
            exam["countdown_status"] = "upcoming"
            exam["countdown_display"] = f"In {days_diff} days"

        enriched.append(exam)

    return enriched


@app.route("/exams")
@login_required
def exams():
    all_exams = get_exams_by_user(session["user_id"])
    all_exams = enrich_exams_with_countdown_info(all_exams)

    upcoming_exams = [e for e in all_exams if e["is_upcoming"]]
    past_exams = sorted(
        (e for e in all_exams if not e["is_upcoming"]),
        key=lambda e: e["exam_date"], reverse=True,
    )

    return render_template(
        "exams.html",
        upcoming_exams=upcoming_exams,
        past_exams=past_exams,
    )


@app.route("/exams/add", methods=["GET", "POST"])
@login_required
def add_exam():
    user_subjects = get_subjects_by_user(session["user_id"])

    if request.method == "POST":
        subject_id = request.form.get("subject_id", "")
        title = request.form.get("title", "").strip()
        exam_date_raw = request.form.get("exam_date", "").strip()
        location = request.form.get("location", "").strip()
        notes = request.form.get("notes", "").strip()

        errors = []

        if not user_subjects:
            errors.append("Add a subject before scheduling an exam.")

        if not subject_id:
            errors.append("Please choose a subject.")

        if not title:
            errors.append("Title is required.")
        elif len(title) > 120:
            errors.append("Title must be 120 characters or fewer.")

        exam_date, exam_date_error = parse_exam_date(exam_date_raw)
        if exam_date_error:
            errors.append(exam_date_error)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "add_exam.html",
                subjects=user_subjects,
                subject_id=subject_id, title=title, location=location, notes=notes,
                exam_date=exam_date_raw,
            )

        new_id = create_exam(
            int(subject_id), session["user_id"],
            title, exam_date, location, notes,
        )

        if new_id is None:
            flash("That subject isn't yours - please pick again.", "error")
            return render_template(
                "add_exam.html",
                subjects=user_subjects,
                subject_id=subject_id, title=title, location=location, notes=notes,
                exam_date=exam_date_raw,
            )

        flash("Exam added successfully.", "success")
        return redirect(url_for("exams"))

    return render_template("add_exam.html", subjects=user_subjects)


@app.route("/exams/edit/<int:exam_id>", methods=["GET", "POST"])
@login_required
def edit_exam(exam_id):
    exam = get_exam_by_id(exam_id, session["user_id"])
    if exam is None:
        flash("That exam doesn't exist or isn't yours to edit.", "error")
        return redirect(url_for("exams"))

    user_subjects = get_subjects_by_user(session["user_id"])

    if request.method == "POST":
        subject_id = request.form.get("subject_id", "")
        title = request.form.get("title", "").strip()
        exam_date_raw = request.form.get("exam_date", "").strip()
        location = request.form.get("location", "").strip()
        notes = request.form.get("notes", "").strip()

        errors = []

        if not subject_id:
            errors.append("Please choose a subject.")

        if not title:
            errors.append("Title is required.")
        elif len(title) > 120:
            errors.append("Title must be 120 characters or fewer.")

        exam_date, exam_date_error = parse_exam_date(exam_date_raw)
        if exam_date_error:
            errors.append(exam_date_error)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "edit_exam.html",
                exam=exam, subjects=user_subjects,
                subject_id=subject_id, title=title, location=location, notes=notes,
                exam_date=exam_date_raw,
            )

        updated = update_exam(
            exam_id, session["user_id"], int(subject_id),
            title, exam_date, location, notes,
        )

        if not updated:
            flash("That subject isn't yours - please pick again.", "error")
            return render_template(
                "edit_exam.html",
                exam=exam, subjects=user_subjects,
                subject_id=subject_id, title=title, location=location, notes=notes,
                exam_date=exam_date_raw,
            )

        flash("Exam updated successfully.", "success")
        return redirect(url_for("exams"))

    return render_template("edit_exam.html", exam=exam, subjects=user_subjects)


@app.route("/exams/delete/<int:exam_id>", methods=["POST"])
@login_required
def delete_exam_route(exam_id):
    deleted = delete_exam(exam_id, session["user_id"])
    if deleted:
        flash("Exam deleted.", "success")
    else:
        flash("That exam doesn't exist or isn't yours to delete.", "error")
    return redirect(url_for("exams"))


# ==========================================================================
# Profile (view, edit, change password)
# ==========================================================================

@app.route("/profile")
@login_required
def profile():
    user_id = session["user_id"]
    return render_template(
        "profile.html",
        stats=get_dashboard_stats(user_id),
    )


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    user_id = session["user_id"]

    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip().lower()

        errors = []

        if not fullname:
            errors.append("Full name is required.")

        if not email:
            errors.append("Email is required.")
        elif not EMAIL_REGEX.match(email):
            errors.append("Please enter a valid email address.")

        # Only hit the database for the uniqueness check once the basics pass
        if not errors:
            existing = get_user_by_email(email)
            if existing is not None and existing["id"] != user_id:
                errors.append("An account with this email already exists.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "edit_profile.html", fullname=fullname, email=email,
            )

        updated = update_user_profile(user_id, fullname, email)
        if not updated:
            flash("An account with this email already exists.", "error")
            return render_template(
                "edit_profile.html", fullname=fullname, email=email,
            )

        session["fullname"] = fullname
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    user = get_user_by_id(user_id)
    return render_template(
        "edit_profile.html",
        fullname=user["fullname"], email=user["email"],
    )


@app.route("/profile/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user_id = session["user_id"]

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_new_password = request.form.get("confirm_new_password", "")

        user = get_user_by_id(user_id)
        errors = []

        if not current_password:
            errors.append("Current password is required.")
        elif user is None or not check_password_hash(user["password"], current_password):
            errors.append("Current password is incorrect.")

        if not new_password:
            errors.append("New password is required.")
        elif len(new_password) < 6:
            errors.append("New password must be at least 6 characters long.")

        if new_password != confirm_new_password:
            errors.append("New passwords do not match.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("change_password.html")

        update_user_password(user_id, generate_password_hash(new_password))
        flash("Password changed successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("change_password.html")


# ==========================================================================
# Calendar
# ==========================================================================

@app.route("/calendar")
@login_required
def calendar_view():
    today = date.today()

    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
    except ValueError:
        year, month = today.year, today.month

    # Normalize an out-of-range month (e.g. prev/next crossing a year boundary)
    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    first_of_month = date(year, month, 1)
    last_of_month = date(year, month, monthrange(year, month)[1])

    try:
        selected_date = datetime.strptime(request.args.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        selected_date = today if (today.year == year and today.month == month) else first_of_month

    # Full weeks (Monday-first) covering the month, including the
    # leading/trailing days borrowed from the adjacent months.
    grid_dates = list(Calendar(firstweekday=0).itermonthdates(year, month))
    range_start, range_end = grid_dates[0], grid_dates[-1]

    events_by_date = get_calendar_events(
        session["user_id"], range_start.isoformat(), range_end.isoformat()
    )

    weeks = []
    week = []
    for day in grid_dates:
        day_events = events_by_date.get(day.isoformat(), [])
        week.append({
            "iso": day.isoformat(),
            "day_number": day.day,
            "in_month": day.month == month,
            "is_today": day == today,
            "is_selected": day == selected_date,
            "events": day_events[:4],
            "extra_count": max(0, len(day_events) - 4),
        })
        if len(week) == 7:
            weeks.append(week)
            week = []

    prev_month_date = first_of_month - timedelta(days=1)
    next_month_date = last_of_month + timedelta(days=1)

    return render_template(
        "calendar.html",
        weeks=weeks,
        weekday_labels=CALENDAR_WEEKDAY_LABELS,
        month_name=first_of_month.strftime("%B"),
        year=year, month=month,
        prev_year=prev_month_date.year, prev_month=prev_month_date.month,
        next_year=next_month_date.year, next_month=next_month_date.month,
        today_year=today.year, today_month=today.month,
        selected_date=selected_date,
        selected_date_label=f"{selected_date.strftime('%A')}, {format_friendly_date(selected_date)}",
        selected_events=events_by_date.get(selected_date.isoformat(), []),
    )


if __name__ == "__main__":
    app.run(debug=True)
