# Study Planner

A Flask web app for tracking subjects, assignments, exams, and study time
in one place. Server-rendered with Jinja templates, styled with a custom
CSS design system (light/dark mode), and backed by SQLite.

## Features

- **Authentication** — register, log in, log out, edit profile, change
  password. Passwords are hashed with Werkzeug; sessions are used to
  track the logged-in user.
- **Dashboard** — at-a-glance stats (subjects, due today, overdue,
  completed, upcoming exams), today's tasks, upcoming exams, per-subject
  progress bars, recent activity feed, and a quick-add form for tasks.
- **Subjects** — create, edit, delete, each with a name, teacher, and
  color used throughout the app.
- **Assignments** — create, edit, delete, mark status (Pending / In
  Progress / Completed), with search and status/priority filters.
- **Exams** — create, edit, delete, with a live countdown ("In 3 days",
  "Today!", "2 days ago"), search, and an upcoming/past filter.
- **Calendar** — a month view combining assignment deadlines, exam
  dates, and study sessions as color-coded dots, with day-by-day
  navigation and a detail panel for the selected date.

Every record is scoped to the logged-in user, so one student can never
see or modify another student's data.

## Getting started

```bash
# 1. Create and activate a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py
```

The app starts on `http://127.0.0.1:5000`. A SQLite database is created
automatically on first run at `database/database.db` (this folder is
gitignored, so it's rebuilt fresh on each clone).

## Project structure

```
study-planner/
├── app.py              # Flask routes, request handling, validation
├── database.py         # SQLite connection, schema, data-access helpers
├── requirements.txt
├── static/
│   ├── css/             # Design system (style.css) + auth pages (auth.css)
│   ├── js/               # Sidebar/dark-mode toggles, flash messages, etc.
│   └── images/
└── templates/           # Jinja templates (one per page/form)
```

## Tech stack

- [Flask](https://flask.palletsprojects.com/) — web framework
- SQLite (via the standard library `sqlite3`) — storage, no ORM
- [Werkzeug](https://werkzeug.palletsprojects.com/) — password hashing
- Vanilla HTML/CSS/JS on the frontend — no build step required

## Notes

- `app.config["SECRET_KEY"]` in `app.py` is a placeholder for local
  development only — replace it with a securely generated value (e.g.
  from an environment variable) before deploying anywhere public.
