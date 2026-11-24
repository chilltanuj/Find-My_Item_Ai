import os
import re
import uuid
import logging
from pathlib import Path
from datetime import date

import streamlit as st
import pandas as pd
from PIL import Image, ImageOps

from database import (
    initialize_database, create_user, get_user_by_email, get_user_by_id,
    create_report, get_reports, get_user_reports, get_report,
    create_claim, get_claims_for_user, update_claim_status,
    get_all_claims, get_admin_stats, admin_reports
)
from security import hash_password, verify_password

try:
    from matching import rank_matches
    MATCHING_ERROR = None
except Exception as exc:  # e.g. sklearn/scipy DLL blocked by a Windows policy
    rank_matches = None
    MATCHING_ERROR = str(exc)

logger = logging.getLogger("findmyitem")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

st.set_page_config(
    page_title="FindMyItem AI",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded"
)
initialize_database()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: #080D17; color: #E8EEF9; }
[data-testid="stSidebar"] { background: #0D1524; border-right: 1px solid #1C2A40; }
.block-container { padding-top: 1.8rem; max-width: 1450px; }
.hero {
  padding: 28px; border: 1px solid #1D3556; border-radius: 20px;
  background: linear-gradient(120deg, #101D32, #0B1423 65%, #102747);
  margin-bottom: 22px;
}
.hero h1 { color: #F4F8FF; font-size: 2.2rem; margin: 0; }
.hero p { color: #9FB2CC; margin: 8px 0 0 0; }
.metric-card {
  background: #101B2C; border: 1px solid #1D2D45;
  border-radius: 16px; padding: 18px;
}
.metric-label { color: #91A4BE; font-size: .85rem; }
.metric-value { color: #F3F7FF; font-size: 1.8rem; font-weight: 800; }
.small-muted { color: #9FB0C6; font-size: .86rem; }
div.stButton > button {
  border-radius: 10px; border: 1px solid #2C65A6;
  background: #1556A0; color: white; font-weight: 650;
}
div.stButton > button:hover { background: #1D70C9; border-color: #5CA8F4; color: white; }
[data-testid="stForm"] { border: 1px solid #22334D; border-radius: 14px; padding: 18px; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def to_dict(row):
    """sqlite3.Row -> plain dict (Rows cannot be deep-copied by Streamlit widgets)."""
    return dict(row) if row is not None else None


def to_dicts(rows):
    return [dict(r) for r in (rows or [])]


def esc(value):
    """Escape user text so it can't inject markdown / LaTeX ($) / emoji shortcodes."""
    if value is None:
        return ""
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", str(value))


def hero(title, subtitle):
    # Titles/subtitles here are static strings written by us, never user input.
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True
    )


def metric_card(label, value):
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div></div>',
        unsafe_allow_html=True
    )


def current_user():
    uid = st.session_state.get("user_id")
    return to_dict(get_user_by_id(uid)) if uid else None


def save_upload(uploaded_file):
    """Returns saved path, or None (an error is shown if the file was rejected)."""
    if uploaded_file is None:
        return None
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        st.error("Please upload a JPG, PNG or WEBP image.")
        return None
    if uploaded_file.size > 8 * 1024 * 1024:
        st.error("Image must be smaller than 8 MB.")
        return None
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)  # fix rotated phone photos
        image = image.convert("RGB")
        filename = f"{uuid.uuid4().hex}.jpg"
        target = UPLOAD_DIR / filename
        image.save(target, format="JPEG", quality=88)
        return str(target)
    except Exception:
        logger.exception("Image processing failed")
        st.error("The uploaded image could not be processed.")
        return None


def show_report(report, show_owner=False):
    with st.container(border=True):
        st.markdown(f"**{esc(report.get('item_name'))}** · {esc(report.get('report_type'))}")
        st.caption(
            f"{esc(report.get('category'))}  •  {esc(report.get('location'))}  •  "
            f"{esc(report.get('incident_date'))}"
        )
        st.markdown(esc(report.get("description")))
        image_path = report.get("image_path")
        if image_path and Path(image_path).exists():
            st.image(image_path, width=240)
        if show_owner:
            st.caption(f"Reported by: {esc(report.get('reporter_name') or 'You')}")


def flash_message():
    msg = st.session_state.pop("flash", None)
    if msg:
        st.success(msg)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
def auth_screen():
    st.markdown("""
    <div class="hero">
      <h1>🔎 FindMyItem AI</h1>
      <p>Find lost belongings. Verify ownership. Bring things back.</p>
    </div>
    """, unsafe_allow_html=True)
    login_tab, register_tab = st.tabs(["Login", "Create account"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email address")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            user = to_dict(get_user_by_email(email.strip().lower()))
            if user and verify_password(password, user["password_hash"]):
                st.session_state.user_id = user["id"]
                st.rerun()
            else:
                st.error("Incorrect email or password.")

    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email address", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            confirm = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            name = name.strip()
            email = email.strip().lower()
            if not name or not email or not password:
                st.error("Please complete all fields.")
            elif not EMAIL_RE.match(email):
                st.error("Enter a valid email address.")
            elif len(password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif get_user_by_email(email):
                st.error("An account with this email already exists.")
            else:
                admin_email = os.getenv("FMI_ADMIN_EMAIL", "").strip().lower()
                role = "admin" if admin_email and email == admin_email else "user"
                try:
                    create_user(name, email, hash_password(password), role)
                    st.success("Account created. Please log in.")
                except Exception:
                    logger.exception("create_user failed")
                    st.error("Could not create the account. Please try again.")
    st.stop()


user = current_user()
if not user:
    auth_screen()

is_admin = user.get("role") == "admin"

with st.sidebar:
    st.markdown("## 🔎 FindMyItem AI")
    st.caption(f"Signed in as **{esc(user['name'])}**")
    page = st.radio(
        "Navigation",
        ["Overview", "Report an item", "Browse reports", "AI matching",
         "Claims & verification"] + (["Admin panel"] if is_admin else []),
        label_visibility="collapsed"
    )
    st.divider()
    if st.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
if page == "Overview":
    hero("Welcome back 👋", "Your personal lost-and-found command center.")
    mine = to_dicts(get_user_reports(user["id"]))
    lost_count = sum(1 for r in mine if r.get("report_type") == "Lost")
    found_count = sum(1 for r in mine if r.get("report_type") == "Found")
    claims = to_dicts(get_claims_for_user(user["id"]))
    cols = st.columns(4)
    metrics = [("My reports", len(mine)), ("Lost reports", lost_count),
               ("Found reports", found_count), ("My claims", len(claims))]
    for col, (label, value) in zip(cols, metrics):
        with col:
            metric_card(label, value)
    st.subheader("Your recent reports")
    if not mine:
        st.info("You haven't submitted any reports yet. Start by reporting a lost or found item.")
    else:
        for report in mine[:5]:
            show_report(report)


elif page == "Report an item":
    hero("Report an item", "Share enough detail to help our matching engine find the right report.")
    flash_message()

    # The report type lives OUTSIDE the form: widgets inside a form don't trigger
    # reruns, so the "private clue" box would never appear/disappear on change.
    report_type = st.radio("Report type", ["Lost", "Found"], horizontal=True, key="report_type_sel")

    # Changing the nonce gives the form fresh (empty) widgets after a successful
    # submit, while keeping the user's input if validation fails.
    nonce = st.session_state.setdefault("report_form_nonce", 0)
    def k(name):
        return f"{name}_{nonce}"

    with st.form(f"report_form_{nonce}"):
        c1, c2 = st.columns(2)
        with c1:
            item_name = st.text_input("Item name", placeholder="e.g. Black Samsung smartphone", key=k("item_name"))
            category = st.selectbox("Category", [
                "Electronics", "Wallet / Purse", "ID / Documents", "Keys",
                "Bag", "Clothing", "Jewellery", "Books / Stationery", "Other"
            ], key=k("category"))
            location = st.text_input("Where was it lost/found?", placeholder="e.g. MAIT library, Delhi", key=k("location"))
            incident_date = st.date_input("Date of incident", value=date.today(),
                                          max_value=date.today(), key=k("incident_date"))
        with c2:
            latitude = st.number_input("Latitude (optional)", min_value=-90.0, max_value=90.0,
                                       value=0.0, format="%.6f", key=k("lat"))
            longitude = st.number_input("Longitude (optional)", min_value=-180.0, max_value=180.0,
                                        value=0.0, format="%.6f", key=k("lon"))
            image_file = st.file_uploader("Item photograph (JPG, PNG, WEBP; max 8 MB)",
                                          type=["jpg", "jpeg", "png", "webp"], key=k("image"))
        description = st.text_area(
            "Description",
            placeholder="Describe colour, brand, model, appearance and other visible details.",
            key=k("description")
        )
        private_clue = ""
        if report_type == "Lost":
            private_clue = st.text_area(
                "Private ownership clue (never shown in public reports)",
                placeholder="Enter a distinctive detail that can help verify ownership. "
                            "Do not enter passwords, PINs or sensitive data.",
                key=k("private_clue")
            )
        agree = st.checkbox(
            "I confirm that this report is accurate and I have the right to share this information.",
            key=k("agree")
        )
        submitted = st.form_submit_button("Submit report", use_container_width=True)

    if submitted:
        if not item_name.strip() or not location.strip() or not description.strip():
            st.error("Item name, location and description are required.")
        elif not agree:
            st.error("Please confirm the report information.")
        else:
            image_path = save_upload(image_file)
            if image_file is not None and image_path is None:
                pass  # save_upload already showed the error; let the user fix the photo
            else:
                coords_ok = not (latitude == 0.0 and longitude == 0.0)
                try:
                    report_id = create_report({
                        "user_id": user["id"], "report_type": report_type,
                        "item_name": item_name.strip(), "category": category,
                        "description": description.strip(), "location": location.strip(),
                        "latitude": latitude if coords_ok else None,
                        "longitude": longitude if coords_ok else None,
                        "incident_date": incident_date.isoformat(),
                        "image_path": image_path,
                        "private_clue": private_clue.strip() or None
                    })
                    st.session_state["flash"] = f"Report #{report_id} submitted successfully."
                    st.session_state["report_form_nonce"] = nonce + 1
                    st.rerun()
                except Exception:
                    logger.exception("create_report failed")
                    st.error("Could not save the report. Please try again.")


elif page == "Browse reports":
    hero("Browse reports", "Explore open lost and found reports shared by the community.")
    filter_type = st.selectbox("Show reports", ["All", "Lost", "Found"])
    search = st.text_input("Search by item, category, description or location").strip().lower()
    rows = to_dicts(get_reports(None if filter_type == "All" else filter_type, exclude_user_id=None))
    filtered = []
    for r in rows:
        haystack = " ".join(
            str(r.get(f) or "") for f in ("item_name", "category", "description", "location")
        ).lower()
        if search in haystack:
            filtered.append(r)
    st.caption(f"{len(filtered)} report(s) found")
    if not filtered:
        st.info("No reports match your search.")
    for r in filtered:
        show_report(r, show_owner=True)


elif page == "AI matching":
    hero("AI matching engine", "Rank possible lost-and-found matches using text, image and optional location similarity.")
    if rank_matches is None:
        st.error(
            "The matching engine could not be loaded on this machine, so AI matching is "
            "unavailable. The rest of the app still works."
        )
        st.caption(f"Details: {esc(MATCHING_ERROR)}")
        st.stop()
    mine = to_dicts(get_user_reports(user["id"]))
    lost_items = [r for r in mine if r.get("report_type") == "Lost" and r.get("status") == "Open"]
    found_items = [r for r in mine if r.get("report_type") == "Found" and r.get("status") == "Open"]
    if not lost_items and not found_items:
        st.info("Submit a lost or found report first to run AI matching.")
    else:
        direction = st.radio("Find matches for", ["My lost item", "My found item"], horizontal=True)
        source_list = lost_items if direction == "My lost item" else found_items
        if source_list:
            source_by_id = {r["id"]: r for r in source_list}
            chosen_id = st.selectbox(
                "Select your report",
                list(source_by_id.keys()),
                format_func=lambda rid: f"#{rid} · {source_by_id[rid]['item_name']}"
            )
            chosen = source_by_id[chosen_id]
            opposite = "Found" if direction == "My lost item" else "Lost"
            candidates = [
                c for c in to_dicts(get_reports(opposite, exclude_user_id=user["id"]))
                if c.get("status", "Open") == "Open"
            ]
            results = []
            try:
                with st.spinner("Comparing reports..."):
                    results = rank_matches(chosen, candidates) if candidates else []
            except Exception:
                logger.exception("rank_matches failed")
                st.error("The matching engine hit a problem. Please try again later.")
            if not results:
                st.info(f"No open {opposite.lower()} reports are available yet.")
            else:
                st.subheader("Ranked potential matches")
                st.caption("Scores are similarity estimates, not proof that two reports concern the same object.")
                for result in results:
                    r = to_dict(result["report"])
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**#{r['id']} · {esc(r.get('item_name'))}**")
                            st.caption(
                                f"{esc(r.get('category'))} · {esc(r.get('location'))} · "
                                f"{esc(r.get('incident_date'))}"
                            )
                            st.markdown(esc(r.get("description")))
                            image_path = r.get("image_path")
                            if image_path and Path(image_path).exists():
                                st.image(image_path, width=190)
                        with c2:
                            st.metric("Match score", f"{result.get('score', 0)}%")
                            if result.get("text_score") is not None:
                                st.caption(f"Text: {result['text_score']}%")
                            if result.get("image_score") is not None:
                                st.caption(f"Image: {result['image_score']}%")
                            if result.get("distance_km") is not None:
                                st.caption(f"Distance: {result['distance_km']} km")
                            st.caption(f"Reporter: {esc(r.get('reporter_name') or 'Unknown')}")
        else:
            st.info("You don't have an open report of this type yet.")


elif page == "Claims & verification":
    hero("Claims & verification", "Submit an ownership claim or review a claim for an item you found.")
    flash_message()
    my_lost = [r for r in to_dicts(get_user_reports(user["id"]))
               if r.get("report_type") == "Lost" and r.get("status") == "Open"]
    found_reports = [r for r in to_dicts(get_reports("Found", exclude_user_id=user["id"]))
                     if r.get("status", "Open") == "Open"]

    st.subheader("Submit a claim")
    if my_lost and found_reports:
        my_lost_by_id = {r["id"]: r for r in my_lost}
        found_by_id = {r["id"]: r for r in found_reports}
        with st.form("claim_form"):
            lost_id = st.selectbox(
                "Your lost-item report",
                list(my_lost_by_id.keys()),
                format_func=lambda rid: f"#{rid} · {my_lost_by_id[rid]['item_name']}"
            )
            found_id = st.selectbox(
                "Found-item report",
                list(found_by_id.keys()),
                format_func=lambda rid: (
                    f"#{rid} · {found_by_id[rid]['item_name']} · {found_by_id[rid]['location']}"
                )
            )
            proof = st.text_area(
                "Describe distinctive details that help establish ownership",
                placeholder="Do not include passwords, PINs, or financial information."
            )
            claim_submit = st.form_submit_button("Submit ownership claim")
        if claim_submit:
            if not proof.strip():
                st.error("Please provide ownership details.")
            else:
                try:
                    create_claim(lost_id, found_id, user["id"], proof.strip())
                    st.success("Claim submitted. The finder can review your explanation.")
                except Exception:
                    logger.exception("create_claim failed")
                    st.warning("A claim for this pair of reports may already exist.")
    else:
        st.info("You need an open lost report and another user's found report before submitting a claim.")

    st.subheader("Claims involving your reports")
    claims = to_dicts(get_claims_for_user(user["id"]))
    if not claims:
        st.info("No claims yet.")
    for claim in claims:
        with st.container(border=True):
            st.markdown(
                f"**Claim #{claim['id']} · {esc(claim.get('lost_item'))} ↔ {esc(claim.get('found_item'))}**"
            )
            st.caption(f"Claimant: {esc(claim.get('claimant_name'))} · Status: {esc(claim.get('status'))}")
            st.markdown(esc(claim.get("proof_text")))
            if claim.get("reviewer_note"):
                st.caption(f"Review note: {esc(claim['reviewer_note'])}")
            # Only the owner of the found report may make the decision.
            if claim.get("finder_id") == user["id"] and claim.get("status") == "Pending":
                note = st.text_input("Review note (optional)", key=f"note_{claim['id']}")
                a, b = st.columns(2)
                with a:
                    if st.button("Approve claim", key=f"approve_{claim['id']}"):
                        update_claim_status(claim["id"], "Approved", note)
                        st.session_state["flash"] = "Claim approved."
                        st.rerun()
                with b:
                    if st.button("Reject claim", key=f"reject_{claim['id']}"):
                        update_claim_status(claim["id"], "Rejected", note)
                        st.session_state["flash"] = "Claim rejected."
                        st.rerun()


elif page == "Admin panel" and is_admin:
    hero("Admin dashboard", "Platform overview and moderation tools.")
    stats = dict(get_admin_stats() or {})
    if stats:
        cols = st.columns(len(stats))
        for col, (label, value) in zip(cols, stats.items()):
            with col:
                metric_card(str(label).replace("_", " ").title(), value)
    st.subheader("All reports")
    report_rows = to_dicts(admin_reports())
    if report_rows:
        st.dataframe(pd.DataFrame(report_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No reports yet.")
    st.subheader("All claims")
    claim_rows = to_dicts(get_all_claims())
    if claim_rows:
        st.dataframe(pd.DataFrame(claim_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No claims yet.")
