# FindMyItem AI — Fresh Streamlit MVP

## 1. Requirements
- Python 3.11 or 3.12 recommended
- Windows, macOS or Linux
- Internet connection for installing packages and loading the optional Google font

## 2. Create and activate a virtual environment (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If Python 3.11 is not installed, install it first. Python 3.12 is also a good option.

## 3. Run

```powershell
streamlit run app.py
```

## 4. Create an admin account (optional)

Before registering the admin account, set the email that should receive the admin role:

```powershell
$env:FMI_ADMIN_EMAIL="admin@example.com"
streamlit run app.py
```

Register using that exact email. Other registrations receive the normal user role.

## Included in this first runnable version
- User registration and login
- Password hashing with PBKDF2
- Lost and found reports
- Private ownership clue field on lost reports (not displayed in public report cards)
- Image uploads
- Browse and search reports
- TF-IDF text similarity matching
- Perceptual image-hash similarity (pHash)
- Optional distance scoring when coordinates are supplied
- Claim submission and finder review
- Basic admin overview

## Important limitations
- Match percentages are heuristic similarity scores, not calibrated probabilities or proof of ownership.
- pHash compares visual appearance; it is not a semantic image AI model like CLIP.
- Ownership clues are kept private from public report listings. This MVP does not yet implement automated clue-answer verification, rate limits, email alerts, password reset, or production-grade audit logging.
- This local SQLite MVP is for development/demo use. Before public deployment, add stronger authorization checks, upload scanning, rate limiting, secure secret management, backups, and production database/storage.

## Project structure
```text
FindMyItem_AI/
├── app.py
├── database.py
├── matching.py
├── security.py
├── requirements.txt
├── README.md
├── data/
└── uploads/
```
