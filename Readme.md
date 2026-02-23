# ⚓ Marine Quiz -- Backend & Admin Dashboard

Marine Quiz is a role-based assessment system designed for Merchant Navy
ranks. It allows users to attempt rank-specific quizzes across 7
competency sections and enables admin users to monitor performance
analytics.

------------------------------------------------------------------------

## 🌐 Live Backend

https://marine-quiz.onrender.com

------------------------------------------------------------------------

# 🧠 Features

## 👤 User Side

-   Register using email + username
-   Attempt quizzes for:
    -   Master
    -   Chief Officer
    -   Chief Engineer
    -   2nd Engineer
    -   Deck Rating (AB/OS)
-   7 assessment sections per attempt
-   Dynamic question count per section
-   Automatic pass/fail calculation (70% pass criteria)
-   Attempt history stored per user

------------------------------------------------------------------------

## 🛠 Admin Dashboard

-   Secure login
-   View:
    -   Total registered users
    -   Total attempts
    -   Total passes
    -   Overall pass rate
-   Filter by rank, username, or email
-   Expand per-user attempts
-   Section-wise breakdown with percentage bars
-   Best score per user

------------------------------------------------------------------------

# 🗄 Database Structure (Supabase)

## app_users

-   id (bigint, PK)
-   username (text)
-   email (text, unique)
-   created_at (timestamptz, default now())

## ranks

-   id (bigint, PK)
-   name (text, unique)
-   pass_percentage (int, default 70)

## sections

-   id (bigint, PK)
-   name (text)
-   order_no (int)

## results

-   id (bigint, PK)
-   user_id (FK → app_users.id)
-   rank_id (FK → ranks.id)
-   attempt_uid (uuid)
-   attempted_at (timestamptz)
-   total_questions (int)
-   total_correct (int)
-   percentage (int)
-   pass (boolean)

## result_sections

-   result_id (FK → results.id)
-   section_id (FK → sections.id)
-   total_questions (int)
-   correct_answers (int)
-   percentage (int)

------------------------------------------------------------------------

# 🔌 API Endpoints

## POST /check_credentials

Creates or validates a user.

## POST /create_score

Stores a full quiz attempt with section breakdown.

## POST /get_stats

Returns admin dashboard analytics.

------------------------------------------------------------------------

# 🏗 Tech Stack

-   Python 3
-   Flask
-   Flask-CORS
-   Gunicorn
-   Supabase (PostgreSQL)
-   Render (Deployment)

------------------------------------------------------------------------

# ⚙ Deployment (Render)

Build Command: pip install -r requirements.txt

Start Command: gunicorn backend:app --bind 0.0.0.0:\$PORT

------------------------------------------------------------------------

# 🔐 Environment Variables

SUPABASE_URL=your_supabase_url SUPABASE_KEY=your_supabase_secret_key

------------------------------------------------------------------------

# 📊 Pass Criteria

Pass percentage for all ranks: **70%**

------------------------------------------------------------------------

# 👨‍✈️ Developed For

Merchant Navy Professional Competency Verification System
