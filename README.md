# Performance & Health Dashboard + AI Training Plan Coach

A single Streamlit app for Garmin devices (built with a Forerunner 165 in
mind, but works with any Garmin that syncs to Garmin Connect). It has three
pages, shown in the left-hand sidebar:

- **This Week** — the health/performance dashboard: a "Today's Snapshot" row
  (VO2 Max, resting heart rate, HRV, Body Battery, sleep, steps), a
  "This Week: Progress" section covering completed Running/Cycling/Swimming
  activities, and a "This Week: Planned Sessions" section showing this
  week's scheduled running workouts from the AI coach.
- **Current Plan** — set/update your training goals and constraints, make a
  quick mid-week adjustment (injury, time off, etc.), and regenerate your
  plan. Regenerating pushes structured workouts straight to your Garmin
  Connect calendar.
- **Weekly Check-In** — a short weekly form (energy, soreness, injury,
  missed sessions, notes) that feeds into next week's generated plan.

Live Garmin data comes from the [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
library. Plans/feedback/goals are stored in a Postgres database (a free
Supabase project works well) and generated using the Claude API.

## 1. Set up the database

Run `schema.sql` once in your Postgres provider's SQL editor (e.g. Supabase's
SQL editor, free tier is fine). This creates the `weekly_plans`,
`weekly_feedback`, and `athlete_profile` tables the app reads/writes.

## 2. Get the code onto GitHub

Create a new **private** GitHub repository (private since real credentials
live in secrets, not the repo) and upload this folder, keeping the structure:

```
app.py
core/
pages/
requirements.txt
.streamlit/config.toml
schema.sql
```

Do **not** upload `secrets.toml.example` as `secrets.toml` — secrets are
entered directly in Streamlit Cloud's UI (step 3 below).

## 3. Deploy on Streamlit Community Cloud (free)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   GitHub.
2. Click **New app**, pick your repo/branch, and set the main file to
   `app.py`.
3. Open **App settings → Secrets** and paste in:
   ```toml
   GARMIN_EMAIL = "your_garmin_login_email@example.com"
   GARMIN_PASSWORD = "your_garmin_password"
   DATABASE_URL = "postgresql://postgres.abc...:yourpassword@aws-0-...pooler.supabase.com:5432/postgres"
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
4. Deploy. You'll get a permanent URL like
   `https://your-app-name.streamlit.app` — open it on your phone, add it to
   your home screen for an app-like feel, and it'll be there on your laptop
   too. All three pages (This Week, Current Plan, Weekly Check-In) live in
   this one app/URL.

## 4. Optional: automated weekly emails

`.github/workflows/weekly_plan.yml` and `scripts/send_weekly_plan.py` can run
the plan generation on a schedule (e.g. Sunday nights) instead of you opening
**Current Plan** manually each week, and email you the result. This needs the
same secrets as above added as **GitHub repository secrets** too
(Settings → Secrets and variables → Actions), plus `GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, and `RECIPIENT_EMAIL` for sending the email. Note: the
email-sending module (`core/email_sender.py`) referenced by that script
wasn't part of the files used to build this app — add it (or point the
script at whatever email method you prefer) before relying on that workflow.
The Streamlit pages (This Week / Current Plan / Weekly Check-In) work fully
without it.

## 5. Important things to know

- **Login frequency / account safety**: Garmin doesn't publish an official
  personal API, so this uses the same login flow as the Garmin Connect app.
  Logging in too often can trigger Garmin's rate limiting or a temporary
  lock. The dashboard's Garmin client is cached at the server level (once
  per hour at most) no matter how many times the page loads — leave that
  caching in place.
- **Two-factor authentication**: if your Garmin account has MFA enabled,
  the automated login used here won't be able to complete it.
- **"Constantly updated"**: the dashboard re-fetches from Garmin Connect
  every 15 minutes while someone has it open, plus there's a manual
  "Refresh Data" button in the sidebar.
- **Field availability**: Garmin's internal API occasionally renames or
  omits fields depending on your device and firmware. The app shows "-"
  rather than crashing if a metric isn't available for a given day.
- **Planned Sessions**: "This Week: Planned Sessions" only shows `run`
  sessions from the current week's saved plan (bike/swim/strength/rest
  sessions in the plan aren't shown there, since that section is scoped to
  running workouts specifically).

## 6. Local testing (optional, before deploying)

```bash
pip install -r requirements.txt
cp secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with your real credentials
streamlit run app.py
```
