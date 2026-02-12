## ITU OBS Enrollment Helper

This repository contains a small Python script that helps automate course enrollment on
ITU OBS at an exact target time. The script:

- Logs into OBS using a real Chromium browser controlled by Playwright.
- Retrieves a JWT bearer token via the official OBS endpoint.
- Sends a course enrollment request at the exact time you specify.
- Allows additional requests in the same session if needed.

This project is intended for **personal use only**. You are solely responsible for complying
with your university's terms of use, rate limits, and academic integrity policies.

---

## Contents

- `itu_obs_enroll.py`: Main script. Collects user input and sends enrollment requests.
- `obs_login.py`: Helper module that logs into OBS with Playwright and fetches a JWT token.
- `requirements.txt`: Python dependencies.

---

## Installation

1. Make sure Python 3.10+ is installed.
2. Clone the repository:

```bash
git clone <repo-url>
cd itu_obs_enroll
```

3. (Optional but recommended) Create and activate a virtual environment:

```bash
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# veya
source .venv/bin/activate  # macOS / Linux
```

4. Install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Usage

Run the main script:

```bash
python itu_obs_enroll.py
```

The script will ask for the following values in order:

1. **OBS username (email)**
2. **OBS password** (hidden input in the terminal)
3. **Target time** (for example `14:00:00.500`)
4. **ADD (ECRN) CRN list**  
   - Example: `12345, 23456, 34567`  
   - Leave empty to avoid adding any courses.
5. **DROP (SCRN) CRN list**  
   - Example: `11111, 22222`  
   - Leave empty to avoid dropping any courses.

Then:

- `obs_login.py` logs into OBS and calls `/ogrenci/auth/jwt` to obtain a JWT token.
- The script waits until the configured target time and sends a single enrollment request.
- After that, typing `"1"` and pressing Enter will send additional requests with the same session.

---

## Security Notes

- Do not hard-code your username or password in the source code. The script always reads
  credentials from the terminal at runtime.
- If you use an `.env` file locally, make sure it is ignored by git (the provided `.gitignore`
  already contains an `.env` entry) and never commit secrets.
- OBS endpoints and behavior may change over time. If login or token retrieval stops
  working, the logic in `obs_login.py` will need to be updated accordingly.

---

## Legal / Ethical Notice

- This project is not an official ITU product.
- You are fully responsible for how you use this script.
- Make sure you respect your university's automation rules, rate limits and all applicable
  terms of service and academic integrity policies.

