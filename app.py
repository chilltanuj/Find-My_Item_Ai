import os
import re
import uuid
from pathlib import Path
from datetime import date

import streamlit as st
import pandas as pd
from PIL import Image

from database import (
    initialize_database, create_user, get_user_by_email, get_user_by_id,
    create_report, get_reports, get_user_reports, get_report,
    create_claim, get_claims_for_user, update_claim_status,
    get_all_claims, get_admin_stats, admin_reports
)
from security import hash_password, verify_password
from matching import rank_matches

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

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
.item-card {
  background: #101B2C; border: 1px solid #1D2D45;
  border-radius: 14px; padding: 15px; margin-bottom: 12px;
}
.small-muted { color: #9FB0C6; font-size: .86rem; }
div.stButton > button {
  border-radius: 10px; border: 1px solid #2C65A6;
  background: #1556A0; color: white; font-weight: 650;
}
div.stButton > button:hover { background: #1D70C9; border-color: #5CA8F4; color: white; }
[data-testid="stForm"] { border: 1px solid #22334D; border-radius: 14px; padding: 18px; }
</style>
""", unsafe_allow_html=True)

def current_user():
    uid = st.session_state.get("user_id")
    return get_user_by_id(uid) if uid else None

def save_upload(uploaded_file):
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
        image = Image.open(uploaded_file).convert("RGB")
        filename = f"{uuid.uuid4().hex}.jpg"
        target = UPLOAD_DIR / filename
        image.save(target, format="JPEG", quality=88)
        return str(target)
    except Exception:
        st.error("The uploaded image could not be processed.")
        return None

def show_report(report, show_owner=False):
    st.markdown('<div class="item-card">', unsafe_allow_html=True)
    st.markdown(f"**{report['item_name']}** · {report['report_type']}")
    st.caption(f"{report['category']}  •  {report['location']}  •  {report['incident_date']}")
    st.write(report["description"])
    if report["image_path"] and Path(report["image_path"]).exists():
        st.image(report["image_path"], width=240)
    if show_owner:
        st.caption(f"Reported by: {report['reporter_name'] if 'reporter_name' in report.keys() else 'You'}")
    st.markdown('</div>', unsafe_allow_html=True)

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
            user = get_user_by_email(email)
            if user and verify_password(password, user["password_hash"]):
                st.session_state.user_id = user["id"]
                st.success("Login successful.")
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
            if not name.strip() or not email.strip() or not password:
                st.error("Please complete all fields.")
            elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
                st.error("Enter a valid email address.")
            elif len(password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif password != confirm:
                st.error("Passwords do not match.")
            elif get_user_by_email(email):
                st.error("An account with this email already exists.")
            else:
                admin_email = os.getenv("FMI_ADMIN_EMAIL", "").strip().lower()
                role = "admin" if email.strip().lower() == admin_email and admin_email else "user"
                create_user(name, email, hash_password(password), role)
                st.success("Account created. Please log in.")
    st.stop()

user = current_user()
if not user:
    auth_screen()

with st.sidebar:
    st.markdown("## 🔎 FindMyItem AI")
    st.caption(f"Signed in as **{user['name']}**")
    page = st.radio(
        "Navigation",
        ["Overview", "Report an item", "Browse reports", "AI matching",
         "Claims & verification"] + (["Admin panel"] if user["role"] == "admin" else []),
        label_visibility="collapsed"
    )
    st.divider()
    if st.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()

if page == "Overview":
    st.markdown("""
    <div class="hero">
      <h1>Welcome back 👋</h1>
      <p>Your personal lost-and-found command center.</p>
    </div>
    """, unsafe_allow_html=True)
    mine = get_user_reports(user["id"])
    lost_count = sum(1 for r in mine if r["report_type"] == "Lost")
    found_count = sum(1 for r in mine if r["report_type"] == "Found")
    claims = get_claims_for_user(user["id"])
    cols = st.columns(4)
    metrics = [("My reports", len(mine)), ("Lost reports", lost_count),
               ("Found reports", found_count), ("My claims", len(claims))]
    for col, (label, value) in zip(cols, metrics):
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)
    st.subheader("Your recent reports")
    if not mine:
        st.info("You haven't submitted any reports yet. Start by reporting a lost or found item.")
    else:
        for report in mine[:5]:
            show_report(report)

elif page == "Report an item":
    st.markdown('<div class="hero"><h1>Report an item</h1><p>Share enough detail to help our matching engine find the right report.</p></div>', unsafe_allow_html=True)
    with st.form("report_form", clear_on_submit=True):
        report_type = st.radio("Report type", ["Lost", "Found"], horizontal=True)
        c1, c2 = st.columns(2)
        with c1:
            item_name = st.text_input("Item name", placeholder="e.g. Black Samsung smartphone")
            category = st.selectbox("Category", [
                "Electronics", "Wallet / Purse", "ID / Documents", "Keys",
                "Bag", "Clothing", "Jewellery", "Books / Stationery", "Other"
            ])
            location = st.text_input("Where was it lost/found?", placeholder="e.g. MAIT library, Delhi")
            incident_date = st.date_input("Date of incident", value=date.today())
        with c2:
            latitude = st.number_input("Latitude (optional)", min_value=-90.0, max_value=90.0, value=0.0, format="%.6f")
            longitude = st.number_input("Longitude (optional)", min_value=-180.0, max_value=180.0, value=0.0, format="%.6f")
            image_file = st.file_uploader("Item photograph (JPG, PNG, WEBP; max 8 MB)", type=["jpg","jpeg","png","webp"])
        description = st.text_area("Description", placeholder="Describe colour, brand, model, appearance and other visible details.")
        private_clue = ""
        if report_type == "Lost":
            private_clue = st.text_area(
                "Private ownership clue (never shown in public reports)",
                placeholder="Enter a distinctive detail that can help verify ownership. Do not enter passwords, PINs or sensitive data."
            )
        agree = st.checkbox("I confirm that this report is accurate and I have the right to share this information.")
        submitted = st.form_submit_button("Submit report", use_container_width=True)
    if submitted:
        if not item_name.strip() or not location.strip() or not description.strip():
            st.error("Item name, location and description are required.")
        elif not agree:
            st.error("Please confirm the report information.")
        else:
            image_path = save_upload(image_file)
            coords_ok = not (latitude == 0.0 and longitude == 0.0)
            report_id = create_report({
                "user_id": user["id"], "report_type": report_type,
                "item_name": item_name.strip(), "category": category,
                "description": description.strip(), "location": location.strip(),
                "latitude": latitude if coords_ok else None,
                "longitude": longitude if coords_ok else None,
                "incident_date": incident_date.isoformat(),
                "image_path": image_path, "private_clue": private_clue.strip() or None
            })
            st.success(f"Report #{report_id} submitted successfully.")
            st.info("Your private ownership clue is stored separately from public report details.")

elif page == "Browse reports":
    st.markdown('<div class="hero"><h1>Browse reports</h1><p>Explore open lost and found reports shared by the community.</p></div>', unsafe_allow_html=True)
    filter_type = st.selectbox("Show reports", ["All", "Lost", "Found"])
    search = st.text_input("Search by item, category, description or location")
    rows = get_reports(None if filter_type == "All" else filter_type, exclude_user_id=None)
    filtered = []
    for r in rows:
        haystack = f"{r['item_name']} {r['category']} {r['description']} {r['location']}".lower()
        if search.lower() in haystack:
            filtered.append(r)
    st.caption(f"{len(filtered)} report(s) found")
    if not filtered:
        st.info("No reports match your search.")
    for r in filtered:
        show_report(r, show_owner=True)

elif page == "AI matching":
    st.markdown('<div class="hero"><h1>AI matching engine</h1><p>Rank possible lost-and-found matches using text, image and optional location similarity.</p></div>', unsafe_allow_html=True)
    mine = get_user_reports(user["id"])
    lost_items = [r for r in mine if r["report_type"] == "Lost" and r["status"] == "Open"]
    found_items = [r for r in mine if r["report_type"] == "Found" and r["status"] == "Open"]
    if not lost_items and not found_items:
        st.info("Submit a lost or found report first to run AI matching.")
    else:
        direction = st.radio("Find matches for", ["My lost item", "My found item"], horizontal=True)
        source_list = lost_items if direction == "My lost item" else found_items
        if source_list:
            chosen = st.selectbox(
                "Select your report",
                source_list,
                format_func=lambda r: f"#{r['id']} · {r['item_name']}"
            )
            opposite = "Found" if direction == "My lost item" else "Lost"
            candidates = get_reports(opposite, exclude_user_id=user["id"])
            results = rank_matches(chosen, candidates)
            if not results:
                st.info(f"No open {opposite.lower()} reports are available yet.")
            else:
                st.subheader("Ranked potential matches")
                st.caption("Scores are similarity estimates, not proof that two reports concern the same object.")
                for result in results:
                    r = result["report"]
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**#{r['id']} · {r['item_name']}**")
                            st.caption(f"{r['category']} · {r['location']} · {r['incident_date']}")
                            st.write(r["description"])
                            if r["image_path"] and Path(r["image_path"]).exists():
                                st.image(r["image_path"], width=190)
                        with c2:
                            st.metric("Match score", f"{result['score']}%")
                            st.caption(f"Text: {result['text_score']}%")
                            if result["image_score"] is not None:
                                st.caption(f"Image: {result['image_score']}%")
                            if result["distance_km"] is not None:
                                st.caption(f"Distance: {result['distance_km']} km")
                            st.caption(f"Reporter: {r['reporter_name']}")
        else:
            st.info("You don't have an open report of this type yet.")

elif page == "Claims & verification":
    st.markdown('<div class="hero"><h1>Claims & verification</h1><p>Submit an ownership claim or review a claim for an item you found.</p></div>', unsafe_allow_html=True)
    my_lost = [r for r in get_user_reports(user["id"]) if r["report_type"] == "Lost" and r["status"] == "Open"]
    found_reports = get_reports("Found", exclude_user_id=user["id"])
    st.subheader("Submit a claim")
    if my_lost and found_reports:
        with st.form("claim_form"):
            lost_choice = st.selectbox("Your lost-item report", my_lost, format_func=lambda r: f"#{r['id']} · {r['item_name']}")
            found_choice = st.selectbox("Found-item report", found_reports, format_func=lambda r: f"#{r['id']} · {r['item_name']} · {r['location']}")
            proof = st.text_area("Describe distinctive details that help establish ownership", placeholder="Do not include passwords, PINs, or financial information.")
            claim_submit = st.form_submit_button("Submit ownership claim")
        if claim_submit:
            if not proof.strip():
                st.error("Please provide ownership details.")
            else:
                try:
                    create_claim(lost_choice["id"], found_choice["id"], user["id"], proof.strip())
                    st.success("Claim submitted. The finder can review your explanation.")
                except Exception:
                    st.warning("A claim for this pair of reports may already exist.")
    else:
        st.info("You need an open lost report and another user's found report before submitting a claim.")

    st.subheader("Claims involving your reports")
    claims = get_claims_for_user(user["id"])
    if not claims:
        st.info("No claims yet.")
    for claim in claims:
        with st.container(border=True):
            st.markdown(f"**Claim #{claim['id']} · {claim['lost_item']} ↔ {claim['found_item']}**")
            st.caption(f"Claimant: {claim['claimant_name']} · Status: {claim['status']}")
            st.write(claim["proof_text"])
            if claim["reviewer_note"]:
                st.caption(f"Review note: {claim['reviewer_note']}")
            # Only the owner of the found report may make the decision.
            if claim["finder_id"] == user["id"] and claim["status"] == "Pending":
                note = st.text_input("Review note (optional)", key=f"note_{claim['id']}")
                a, b = st.columns(2)
                with a:
                    if st.button("Approve claim", key=f"approve_{claim['id']}"):
                        update_claim_status(claim["id"], "Approved", note)
                        st.success("Claim approved.")
                        st.rerun()
                with b:
                    if st.button("Reject claim", key=f"reject_{claim['id']}"):
                        update_claim_status(claim["id"], "Rejected", note)
                        st.warning("Claim rejected.")
                        st.rerun()

elif page == "Admin panel":
    st.markdown('<div class="hero"><h1>Admin dashboard</h1><p>Platform overview and moderation tools.</p></div>', unsafe_allow_html=True)
    stats = get_admin_stats()
    cols = st.columns(5)
    for col, (label, value) in zip(cols, stats.items()):
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label.title()}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)
    st.subheader("All reports")
    report_rows = admin_reports()
    if report_rows:
        st.dataframe(pd.DataFrame([dict(r) for r in report_rows]), use_container_width=True, hide_index=True)
    st.subheader("All claims")
    claim_rows = get_all_claims()
    if claim_rows:
        st.dataframe(pd.DataFrame([dict(r) for r in claim_rows]), use_container_width=True, hide_index=True)
