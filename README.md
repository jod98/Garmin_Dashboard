# Performance & Health Dashboard

A Streamlit dashboard for Garmin devices (built with a Forerunner 165 in mind,
but works with any Garmin that syncs to Garmin Connect). It shows:

- **Running / Cycling / Swimming** — recent activities, distance trends,
  total time, average and max heart rate, per-session HR chart
- **Health** — resting heart rate, HRV, sleep stages, Body Battery, training
  status/load
- A "Today's Snapshot" row plus a combined multi-sport overview

Data comes live from Garmin Connect using the [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
library — no manual exporting needed.

## 1. Get the code onto GitHub

1. Create a new **private** GitHub repository (private, since your Garmin
   credentials will live in Streamlit's secrets, not the repo — but keep the
   repo private anyway as good practice).
2. Upload these files, keeping the folder structure:
   ```
   app.py
   requirements.txt
   .streamlit/config.toml
   ```
   (Do **not** upload `secrets.toml.example` as `secrets.toml` — secrets are
   entered directly in Streamlit Cloud's UI, step 3 below.)

## 2. Deploy on Streamlit Community Cloud (free)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   GitHub.
2. Click **New app**, pick your repo/branch, and set the main file to
   `app.py`.
3. Before or after deploying, open **App settings → Secrets** and paste:
   ```toml
   GARMIN_EMAIL = "your_garmin_login_email@example.com"
   GARMIN_PASSWORD = "your_garmin_password"
   ```
4. Deploy. You'll get a permanent URL like
   `https://your-app-name.streamlit.app` — open it on your phone, add it to
   your home screen (Share → Add to Home Screen on iOS/Android) for an
   app-like feel, and it'll be there on your laptop too.

## 3. Important things to know

- **Login frequency / account safety**: Garmin doesn't publish an official
  personal API, so this uses the same login flow as the Garmin Connect app.
  Logging in too often can trigger Garmin's rate limiting or a temporary
  lock. The app is built to log in **once per hour at most** (cached at the
  server level) no matter how many times you or others load the page — leave
  that caching in place.
- **Two-factor authentication**: if your Garmin account has MFA enabled,
  the automated login used here won't be able to complete it. Easiest fix:
  temporarily disable MFA on your Garmin account for this to work smoothly,
  or use an [app-specific/API token approach](https://github.com/cyberjunky/python-garminconnect)
  if Garmin adds one in future.
- **"Constantly updated"**: the dashboard re-fetches from Garmin Connect
  every 15 minutes while someone has it open, plus there's a manual
  "Refresh now" button in the sidebar. It does not run in the background
  when nobody has the tab open — Streamlit Community Cloud apps don't run
  a persistent backend job, they run when visited (with a brief cold-start
  the first time it wakes up).
- **Field availability**: Garmin's internal API occasionally renames or
  omits fields (e.g. training load, HRV) depending on your device and
  firmware. The app is written to show "-" rather than crash if a metric
  isn't available for a given day — if you see a lot of dashes on a metric
  you know you have data for, that's worth flagging so the field mapping
  can be adjusted.

## 4. Local testing (optional, before deploying)

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with your real credentials
streamlit run app.py
```
