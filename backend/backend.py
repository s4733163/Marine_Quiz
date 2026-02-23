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


# everytime we do a supabase operation use try catch to catch the api error that can 
# be returned in the json and makes code more neat
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

    email = (payload.get("email") or "").strip().lower()
    rank_name = (payload.get("rank") or "").strip()  # keep original for matching

    # check if the email and rank is present
    if not email or not rank_name:
        return jsonify({"ok": False, "message": "email and rank are required"}), 400

    #  Get user_id from email
    # this returns a list of rows
    # list can be made of a single row only as well
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
    
    # if the data does not exist
    if not (uresp.data or []):
        return jsonify({"ok": False, "message": "User not found for this email"}), 404

    user_id = uresp.data[0]["id"]

    #  Get rank_id (case-insensitive match)
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

    #  Get sections map: section name -> id
    try:
        sresp = supabase.table("sections").select("id,name,order_no").execute()
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error (sections lookup)", "detail": str(e)}), 500
    
    # get all the sections that can be present
    sections = sresp.data or []
    if not sections:
        return jsonify({"ok": False, "message": "No sections configured in database"}), 500

    # Build a case-insensitive lookup
    section_name_to_id = { (s["name"] or "").strip().lower(): s["id"] for s in sections }

    #  Extract section results from payload
    # All keys except "email" and "rank" are treated as section names
    section_payload_keys = [k for k in payload.keys() if k not in ("email", "rank")]

    if not section_payload_keys:
        return jsonify({"ok": False, "message": "No section results found in payload"}), 400

    attempt_group_id = str(uuid.uuid4())
    attempted_at = datetime.now(timezone.utc).isoformat()

    rows_to_insert = []
    missing_sections = []
    bad_sections = []

    # add all the scores for each section corresponding to a user
    for section_key in section_payload_keys:
        section_key_norm = section_key.strip().lower()
        section_id = section_name_to_id.get(section_key_norm)

        # if the section in teh payload does not exist in the db
        if not section_id:
            missing_sections.append(section_key)
            continue

        # get the total questions and the answer numbers
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

        # add the results in the db
        rows_to_insert.append({
            "attempt_group_id": attempt_group_id,
            "user_id": user_id,
            "rank_id": rank_id,
            "section_id": section_id,
            "total_questions": total_q,
            "correct_answers": correct,
            "attempted_at": attempted_at
        })


    # check if there were missing or bad sections
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




@app.route("/get_stats", methods=["POST"])
def get_stats():
    data = request.get_json(force=True) or {}

    email    = (data.get("email")    or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify({"ok": False, "message": "email and password are required"}), 400

    # 1) Verify admin credentials — email + password must match
    try:
        uresp = (
            supabase.table("app_users")
            .select("id, username, email, password")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error", "detail": str(e)}), 500

    rows = uresp.data or []
    if not rows:
        return jsonify({"ok": False, "message": "No account found for this email"}), 404

    admin = rows[0]
    if not admin.get("password") or admin.get("password") != password:
        return jsonify({"ok": False, "message": "Incorrect password"}), 401

    # 2) Fetch ALL results across all users, newest first
    try:
        rresp = (
            supabase.table("results")
            .select("attempt_group_id, user_id, total_questions, correct_answers, attempted_at, rank_id, section_id")
            .order("attempted_at", desc=True)
            .execute()
        )
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error (results)", "detail": str(e)}), 500

    # 3) Fetch all lookup tables in parallel
    try:
        all_users_resp = supabase.table("app_users").select("id, username, email").execute()
        ranks_resp     = supabase.table("ranks").select("id, name").execute()
        sections_resp  = supabase.table("sections").select("id, name").execute()
    except APIError as e:
        return jsonify({"ok": False, "message": "Database error (lookups)", "detail": str(e)}), 500

    user_map    = {u["id"]: u for u in (all_users_resp.data or [])}
    rank_map    = {r["id"]: r["name"] for r in (ranks_resp.data    or [])}
    section_map = {s["id"]: s["name"] for s in (sections_resp.data or [])}

    # 4) Group by user_id, then by attempt_group_id (newest first preserved)
    users_data   = {}   # user_id -> { username, email, attempts: {gid: {...}} }
    users_order  = []   # insertion order of user_ids (by first seen attempt)
    attempt_order = {}  # user_id -> [gid in order]

    for row in (rresp.data or []):
        uid = row["user_id"]
        gid = row["attempt_group_id"]

        if uid not in users_data:
            users_order.append(uid)
            u = user_map.get(uid, {})
            users_data[uid] = {
                "username": u.get("username", "Unknown"),
                "email":    u.get("email",    "Unknown"),
                "attempts": {},
            }
            attempt_order[uid] = []

        if gid not in users_data[uid]["attempts"]:
            attempt_order[uid].append(gid)
            users_data[uid]["attempts"][gid] = {
                "attempt_group_id": gid,
                "rank":             rank_map.get(row["rank_id"], "Unknown"),
                "attempted_at":     row["attempted_at"],
                "total_correct":    0,
                "total_questions":  0,
                "sections":         []
            }

        correct = row["correct_answers"]
        total   = row["total_questions"]
        users_data[uid]["attempts"][gid]["sections"].append({
            "name":    section_map.get(row["section_id"], "Unknown"),
            "correct": correct,
            "total":   total,
            "pct":     round(correct / total * 100) if total else 0
        })
        users_data[uid]["attempts"][gid]["total_correct"]   += correct
        users_data[uid]["attempts"][gid]["total_questions"] += total

    # 5) Finalise each attempt (pct, pass, sorted sections) and build output
    result_users = []
    for uid in users_order:
        ud = users_data[uid]
        attempts_list = []
        for gid in attempt_order[uid]:
            a = ud["attempts"][gid]
            a["sections"].sort(key=lambda s: s["name"])
            t = a["total_questions"]
            c = a["total_correct"]
            a["pct"]  = round(c / t * 100) if t else 0
            a["pass"] = a["pct"] >= 70
            attempts_list.append(a)

        result_users.append({
            "username": ud["username"],
            "email":    ud["email"],
            "attempts": attempts_list
        })

    # Overall summary counts
    total_attempts = sum(len(u["attempts"]) for u in result_users)
    total_passes   = sum(
        sum(1 for a in u["attempts"] if a["pass"])
        for u in result_users
    )

    return jsonify({
        "ok":            True,
        "admin":         {"username": admin["username"], "email": admin["email"]},
        "total_users":   len(result_users),
        "total_attempts": total_attempts,
        "total_passes":  total_passes,
        "users":         result_users
    }), 200

# used to check that the api is active or not
@app.get("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    app.run(debug=True)