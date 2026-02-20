from supabase import create_client
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from postgrest.exceptions import APIError
import os
import uuid
from datetime import datetime, timezone
from flask_cors import CORS


# Load .env file
load_dotenv()

# Get variables
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

# Create client
supabase = create_client(url, key)
app = Flask(__name__)
CORS(app)  # Allow all origins (works for file://, any local server port)

@app.route("/check_credentials", methods=["POST"])
def check():
    data = request.get_json(force=True) or {}

    # Normalize input
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()

    if not username or not email:
        return jsonify({
            "ok": False,
            "message": "username and email are required"
        }), 400

    try:
        # Check if email exists
        resp = (
            supabase
            .table("app_users")
            .select("id, username, email")
            .eq("email", email)
            .limit(1)
            .execute()
        )

    # throw error if db fails to connect
    except APIError as e:
        return jsonify({
            "ok": False,
            "message": "Database error",
            "detail": str(e)
        }), 500

    rows = resp.data or []

    # check if the email and username matches or mismatch
    if rows:
        existing = rows[0]

        # Normalize DB username for safety
        existing_username = (existing.get("username") or "").strip().lower()

        # eisting username exists
        if existing_username == username:
            return jsonify({
                "ok": True,
                "status": "existing_user",
                "user_id": existing["id"],
                "message": "Email and username match"
            }), 200
        else:
            return jsonify({
                "ok": False,
                "status": "username_mismatch",
                "message": "A different username is already registered with this email"
            }), 409

    # Email does not exist → create new user
    try:
        ins = (
            supabase
            .table("app_users")
            .insert({"email": email, "username": username})
            .execute()
        )
    except APIError as e:
        msg = str(e)

        # Now only email uniqueness can conflict
        if "duplicate key value" in msg or "unique" in msg.lower():
            return jsonify({
                "ok": False,
                "status": "conflict",
                "message": "Email already exists"
            }), 409

        return jsonify({"ok": False, "message": "Database error", "detail": msg}), 500

    new_user = (ins.data or [None])[0]

    # new user has been created
    return jsonify({
        "ok": True,
        "status": "created",
        "user_id": new_user["id"],
        "message": "New user created"
    }), 201




@app.route("/create_score", methods=["POST"])
def create_score():
    payload = request.get_json(force=True) or {}

    print(payload)
    email = (payload.get("email") or "").strip().lower()
    rank_name = (payload.get("rank") or "").strip()  # keep original for matching
    if not email or not rank_name:
        return jsonify({"ok": False, "message": "email and rank are required"}), 400

    # 1) Get user_id from email
    try:
        uresp = (
            supabase.table("app_users")
            .select("id,email")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error (user lookup)", "detail": str(e)}), 500

    if not (uresp.data or []):
        return jsonify({"ok": False, "message": "User not found for this email"}), 404

    user_id = uresp.data[0]["id"]

    # 2) Get rank_id (case-insensitive match)
    try:
        rresp = (
            supabase.table("ranks")
            .select("id,name")
            .ilike("name", rank_name)   # case-insensitive
            .limit(1)
            .execute()
        )
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error (rank lookup)", "detail": str(e)}), 500

    if not (rresp.data or []):
        return jsonify({"ok": False, "message": f"Rank not found: {rank_name}"}), 400

    rank_id = rresp.data[0]["id"]

    # 3) Get sections map: section name -> id
    try:
        sresp = supabase.table("sections").select("id,name,order_no").execute()
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error (sections lookup)", "detail": str(e)}), 500

    sections = sresp.data or []
    if not sections:
        return jsonify({"ok": False, "message": "No sections configured in database"}), 500

    # Build a case-insensitive lookup
    section_name_to_id = { (s["name"] or "").strip().lower(): s["id"] for s in sections }

    # 4) Extract section results from payload
    # All keys except "email" and "rank" are treated as section names
    section_payload_keys = [k for k in payload.keys() if k not in ("email", "rank")]

    if not section_payload_keys:
        return jsonify({"ok": False, "message": "No section results found in payload"}), 400

    attempt_group_id = str(uuid.uuid4())
    attempted_at = datetime.now(timezone.utc).isoformat()

    rows_to_insert = []
    missing_sections = []
    bad_sections = []

    for section_key in section_payload_keys:
        section_key_norm = section_key.strip().lower()
        section_id = section_name_to_id.get(section_key_norm)

        if not section_id:
            missing_sections.append(section_key)
            continue

        value = payload.get(section_key) or {}
        if not isinstance(value, dict):
            bad_sections.append({"section": section_key, "error": "Section value must be an object"})
            continue

        total_q = value.get("total_questions")
        correct = value.get("correct_answers")

        # Allow alternative key names if your frontend uses them
        if total_q is None:
            total_q = value.get("total") or value.get("totalQuestions")
        if correct is None:
            correct = value.get("correct") or value.get("correctQuestions")

        try:
            total_q = int(total_q)
            correct = int(correct)
        except (TypeError, ValueError):
            bad_sections.append({"section": section_key, "error": "total_questions and correct_answers must be integers"})
            continue

        if total_q < 0 or correct < 0 or correct > total_q:
            bad_sections.append({"section": section_key, "error": "Invalid counts (ensure 0 <= correct <= total)"})
            continue

        rows_to_insert.append({
            "attempt_group_id": attempt_group_id,
            "user_id": user_id,
            "rank_id": rank_id,
            "section_id": section_id,
            "total_questions": total_q,
            "correct_answers": correct,
            "attempted_at": attempted_at
        })

    if missing_sections:
        return jsonify({
            "ok": False,
            "message": "Some section names are not configured in database",
            "missing_sections": missing_sections
        }), 400

    if bad_sections:
        return jsonify({
            "ok": False,
            "message": "Some section payloads are invalid",
            "errors": bad_sections
        }), 400

    # (Optional) enforce exactly 7 sections, if you want:
    # if len(rows_to_insert) != 7:
    #     return jsonify({"ok": False, "message": f"Expected 7 sections, got {len(rows_to_insert)}"}), 400

    # 5) Insert all rows (one per section)
    try:
        ins = supabase.table("results").insert(rows_to_insert).execute()
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error (insert results)", "detail": str(e)}), 500

    return jsonify({
        "ok": True,
        "status": "created",
        "attempt_group_id": attempt_group_id,
        "user_id": user_id,
        "rank_id": rank_id,
        "rows_inserted": len(ins.data or [])
    }), 201




if __name__ == "__main__":
    app.run(debug=True)