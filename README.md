## ITU OBS Auto Enrollment Script

Simple Python script to automate course enrollment on ITU OBS.

- **TIME mode** – fire once at an exact time (ms precision) for selected CRNs.
- **WATCH mode** – continuously watch quota for selected CRNs and auto-enroll when a seat appears, plus periodic direct enroll attempts.

The script runs in terminal and uses official OBS endpoints.

---

## Quick start

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   # optional but recommended for robust login:
   playwright install chromium
   ```

2. Create `.env` from the template:

   ```bash
   cp .env.example .env
   ```

3. Edit `.env` (minimal setup):

   ```env
   MODE=WATCH               # or TIME
   ITU_USERNAME=your_itu_username
   ITU_PASSWORD=your_itu_password

   TARGET_TIME=14:00:00.400
   TIME_CRNS=EHB:22007,MYZ:23622

   WATCH_CRNS=EHB:23603,MYZ:23622
   ```

4. Run:

   ```bash
   python itu_obs_ders_kayit.py
   ```

---

## Modes and CRN format

- All CRNs are written as **`BRANCH:CRN`**, for example:
  - `EHB:23603`
  - `MYZ:23622`

- The script:
  - Splits these into branch codes (`EHB`, `MYZ`, etc.) and CRNs (`23603`, `23622`).
  - Looks up branch codes in `derskodları.json` to find the correct `bransKoduId`.
  - Calls the appropriate `DersProgramSearch` URLs.
  - Sends **only CRN numbers** to `POST https://obs.itu.edu.tr/api/ders-kayit/v21`.

### TIME mode (`MODE=TIME`)

- Uses `TARGET_TIME` and `TIME_CRNS`.
- At `TARGET_TIME` (with milliseconds) sends a single enrollment request for all `TIME_CRNS`.
- Prints full HTTP response and exits.

### WATCH mode (`MODE=WATCH`)

- Uses `WATCH_CRNS`.
- Continuously:
  - Fetches course tables for all branches referenced in `WATCH_CRNS`.
  - Prints quota for each watched CRN.
  - If available seats exist, sends an enrollment request and prints the response.
  - Additionally, sends a direct enrollment request for all `WATCH_CRNS` every fixed interval.

---

## Files

- `itu_obs_ders_kayit.py` – main script.
- `obs_login.py` – optional Playwright-based login helper.
- `derskodları.json` – mapping of department codes to `bransKoduId`.
- `requirements.txt` – Python dependencies.
- `.env.example` – example environment file (copy to `.env` and edit).

**Important:** never commit your real `.env` (with credentials) to GitHub.

