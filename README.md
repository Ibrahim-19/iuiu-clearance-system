# IUIU Arua Campus — Online Clearance System

A Flask web application that manages graduation clearance for finalists across
the 5 campus offices: **Faculty Dean / HOD**, **University Bursar**,
**University Library**, **Dean of Students**, and **ICT / MIS Department**.

## Tech Stack
- Python / Flask, Flask-SQLAlchemy (SQLite locally, PostgreSQL in production), Flask-Login, Flask-WTF (WTForms), Flask-Mail
- ReportLab (PDF certificates) + `qrcode` (fraud-protection QR codes)
- Cloudinary for persistent file storage in production (receipts, profile photos, certificates) — falls back to local disk automatically when not configured
- Vanilla HTML / CSS / JavaScript — hamburger sidebar nav, live notification bell, client-side table search
- Hosting: built to deploy on Render (see **Deploying to Render** below)

## How the access gate works
1. **Step 1 — Finalist Whitelist:** The Registrar uploads (CSV) or manually adds
   registration numbers to the **Finalist Enrollment List**. A student can only
   register/log in if their reg number is on this active list, *and* the
   computed expected-graduation-year (admission year + course duration) has
   been reached.
   - Course Duration Matrix: Certificate/Diploma = 2 yrs, Bachelor's = 3 yrs, LLB = 4 yrs.
2. **Step 2 — Debt Exception Table:** For each of the 5 departments, if an
   unsettled `DebtRecord` exists for the student's reg number, the dashboard
   shows a **receipt upload field** instead of a simple checkbox.
3. Once all 5 department items are `approved`, the system locks the request,
   generates a PDF certificate (ReportLab) with an embedded QR code, and
   notifies the student.

## Project layout
```
config.py             Central settings (departments, course durations, mail, uploads, Cloudinary, DB)
run.py                 Entry point
seed.py                 Local CLI wrapper for seeding (auto-runs on every boot anyway — see below)
Procfile                Render/Heroku-style start command
render.yaml             Optional Render Blueprint (infra-as-code shortcut)
app/
  __init__.py          App factory: DB creation, column auto-patcher, auto-seeding, Cloudinary init
  seed_data.py          Idempotent seed logic shared between app startup and seed.py
  extensions.py         db / login_manager / mail / csrf
  models.py             User, Department, FinalistWhitelist, DebtRecord,
                         ClearanceRequest, ClearanceItem, Notification
  forms.py              WTForms incl. Gmail-only + reg-number-format validators
  utils.py              Eligibility engine, notifications, CSV import, Cloudinary/local file uploads
  certificate.py         ReportLab PDF + QR code generator (renders to bytes in memory)
  auth/                 Register / login / logout
  student/               Dashboard, clearance submission, profile, certificate
  admin/                 Department admin: review queue, approve/reject, debt ledger
  registrar/             Super Admin: whitelist, staff accounts, master list, overrides
  main/                  Dashboard router, notifications, public certificate verification
  templates/, static/    HTML templates, CSS, JS, bundled Font Awesome icons
```

## Local Setup
```bash
python -m venv venv && source venv/bin/activate   # optional
pip install -r requirements.txt
python run.py          # http://localhost:5000
```
Seeding (Registrar account, 5 department admins, departments, one demo
finalist) now happens **automatically on every app startup** — you don't
need to run `python seed.py` manually anymore. It's idempotent, so it
only creates what's missing each time. (`python seed.py` still exists as
a convenience if you want to trigger it on demand and see the printed
output.)

Locally, with no `DATABASE_URL` or Cloudinary env vars set, everything
falls back to SQLite + local disk storage automatically — no Cloudinary
account needed just to develop on your machine.

**Default Registrar login:** `iuiu.registrar@gmail.com` / `ChangeMe123!` — change this immediately.

**Default department admin logins** (created automatically by `seed.py` so the approval workflow works immediately):

| Department | Email | Password |
|---|---|---|
| Faculty Dean / HOD | `iuiu.facultydean@gmail.com` | `Admin123!` |
| University Bursar | `iuiu.bursar@gmail.com` | `Admin123!` |
| University Library | `iuiu.library@gmail.com` | `Admin123!` |
| Dean of Students | `iuiu.deanofstudents@gmail.com` | `Admin123!` |
| ICT / MIS Department | `iuiu.ict@gmail.com` | `Admin123!` |

Change all of these before going live (Registrar → Department Admins, or the student's own profile page for password changes). All staff accounts (Registrar + department admins) use Gmail addresses, same as students.

The Registrar should then:
1. Go to **Finalist Whitelist** and import the real cohort list (CSV columns:
   `reg_number, student_name, course_type, admission_year`).
2. Confirm/replace the 5 department admin passwords above.
3. Department admins log in and import their **Debt Ledger** (CSV columns:
   `reg_number, amount, reason`) before students start submitting.

Students then register with their Gmail address and registration number in
the format `xxx-xxxxxx-xxxxx`.

## Email
By default `MAIL_SUPPRESS_SEND=1`, so emails are not actually sent (every
action still creates an in-app notification with the bell icon). To enable
real Gmail SMTP delivery, set `MAIL_USERNAME` / `MAIL_PASSWORD` (a Gmail App
Password if 2FA is on) and `MAIL_SUPPRESS_SEND=0` in your environment or a
`.env` file (see `.env.example`).

---

## Deploying to Render + Cloudinary

Render's free web service tier has two limitations this app is built
around: the filesystem is **ephemeral** (wiped on every redeploy/restart),
and there's **no shell access** to run one-off commands after deploy. The
app handles both automatically:
- File uploads (receipts, profile photos, certificates) go to **Cloudinary**
  instead of local disk, so they survive redeploys.
- Database tables and the Registrar/admin accounts are created
  **automatically on every boot** (see `app/__init__.py`) — there is no
  manual seeding step on Render.

### Step 1 — Push the code to GitHub
Render deploys from a Git repository.
```bash
cd iuiu_clearance
git init
git add .
git commit -m "Initial commit"
```
Create a new repository on GitHub, then:
```bash
git remote add origin https://github.com/<your-username>/<your-repo>.git
git branch -M main
git push -u origin main
```

### Step 2 — Create a free Cloudinary account
1. Go to [cloudinary.com](https://cloudinary.com) and sign up (free tier is plenty for this).
2. On your Cloudinary **Dashboard**, find the **Product Environment Credentials** box. Copy:
   - **Cloud name**
   - **API Key**
   - **API Secret**
   You'll paste these into Render in Step 5.

### Step 3 — Create a Render account
Go to [render.com](https://render.com) and sign up (GitHub login is easiest, since it lets Render see your repos directly).

### Step 4 — Create a PostgreSQL database on Render
1. Render Dashboard → **New** → **PostgreSQL**.
2. Give it a name, e.g. `iuiu-clearance-db`. Leave the rest as default. Choose the **Free** plan.
3. Click **Create Database**. Wait for it to spin up.
4. Once it's ready, open it and copy the **Internal Database URL** (you'll need this in Step 5). It looks like `postgres://user:pass@host/dbname`.

> Note: Render's free Postgres plan is deleted after 30 days unless upgraded. For a long-running production system, plan to upgrade this database to a paid plan before then, or take regular backups.

### Step 5 — Create the web service
1. Render Dashboard → **New** → **Web Service**.
2. Connect your GitHub repo from Step 1.
3. Fill in:
   - **Name:** `iuiu-clearance` (or anything)
   - **Region:** closest to your users
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn run:app`
   - **Plan:** Free
4. Under **Environment Variables**, add:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Internal Database URL from Step 4 |
   | `SECRET_KEY` | any long random string (e.g. generate one with `python -c "import secrets; print(secrets.token_hex(32))"`) |
   | `CLOUDINARY_CLOUD_NAME` | from Step 2 |
   | `CLOUDINARY_API_KEY` | from Step 2 |
   | `CLOUDINARY_API_SECRET` | from Step 2 |
   | `CURRENT_ACADEMIC_YEAR` | e.g. `2026` |
   | `MAIL_SUPPRESS_SEND` | `1` (or `0` + Gmail SMTP vars if you want real emails — see Email section above) |

5. Click **Create Web Service**. Render will build and deploy automatically. Watch the **Logs** tab — on first boot you should see lines like:
   ```
   Created Registrar account: iuiu.registrar@gmail.com / ChangeMe123!
   Created department admin: iuiu.bursar@gmail.com / Admin123!  (University Bursar)
   ...
   ```
   That's the auto-seeding running — no manual step needed.

### Step 6 — Log in and lock it down
1. Visit your new Render URL (e.g. `https://iuiu-clearance.onrender.com`).
2. Log in as the Registrar (`iuiu.registrar@gmail.com` / `ChangeMe123!`) and **change the password immediately** (this is a publicly known default).
3. Log in as each department admin and change their passwords too (table of defaults is above).
4. As Registrar, go to **Finalist Whitelist** and import your real cohort list.
5. Once your real data is loaded, set the `SEED_DEMO_DATA` environment variable to `0` on Render (Environment tab → edit → redeploy) so the demo finalist entry stops being checked on every boot.

### About the free tier
- Render's free web service **spins down after 15 minutes of inactivity** and takes ~30–60 seconds to wake up on the next request. For a campus system used a few times a day, this is usually fine — just don't be surprised by a slow first load. Upgrading to a paid instance removes this.
- Cloudinary's free tier gives generous storage/bandwidth for receipts, profile photos, and certificates — more than enough for a single campus's graduating class.

### Updating the live site later
Any `git push` to your connected branch triggers an automatic redeploy on Render. The column auto-patcher in `app/__init__.py` means you can add new fields to a model later and they'll be added to the live Postgres table automatically on the next deploy — no manual migration step required.

### Optional shortcut: render.yaml
This repo includes a `render.yaml` Blueprint file. If you'd rather not click through Steps 4–5 by hand, Render can detect this file and provision the database + web service together — go to **New → Blueprint** on Render and point it at your repo instead. You'll still need to fill in the Cloudinary keys manually afterward (Blueprint env vars marked `sync: false` are intentionally left for you to set).

---

## Notes
- `CURRENT_ACADEMIC_YEAR` in `config.py` (or the env var of the same name) drives the finalist eligibility year check — update each year.
- Locally without Cloudinary configured: receipts go to `app/static/uploads/receipts/`, certificates to `app/static/uploads/certificates/`, profile photos to `app/static/uploads/profiles/`.
- On Render with Cloudinary configured: all three go to Cloudinary instead, under folders `iuiu_clearance/receipts`, `iuiu_clearance/certificates`, `iuiu_clearance/profiles` — survives redeploys.
- `DATABASE_URL` accepts either a `postgres://` or `postgresql://` scheme — `config.py` normalizes it automatically (Render gives you `postgres://`, which older SQLAlchemy versions reject).
