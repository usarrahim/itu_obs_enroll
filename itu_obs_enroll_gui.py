#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Simple graphical frontend for the ITU OBS enrollment script."""

import threading
from typing import List, Optional

import customtkinter as ctk
import requests

from itu_obs_enroll import wait_until, default_headers
from obs_login import get_jwt


DERS_KAYIT_URL = "https://obs.itu.edu.tr/api/ders-kayit/v21"


def parse_crns(value: str) -> List[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


class EnrollApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("ITU OBS Enroll")
        self.geometry("680x520")
        self.resizable(False, False)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build_ui()

    def _build_ui(self) -> None:
        padding = {"padx": 16, "pady": 8}

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        # Title
        title_label = ctk.CTkLabel(
            self.main_frame,
            text="ITU OBS Timed Enrollment",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(4, 16))

        # Username
        ctk.CTkLabel(self.main_frame, text="OBS username (email):").grid(
            row=1, column=0, sticky="e", **padding
        )
        self.username_entry = ctk.CTkEntry(self.main_frame, width=260)
        self.username_entry.grid(row=1, column=1, sticky="w", **padding)

        # Password
        ctk.CTkLabel(self.main_frame, text="OBS password:").grid(
            row=2, column=0, sticky="e", **padding
        )
        self.password_entry = ctk.CTkEntry(self.main_frame, show="*", width=260)
        self.password_entry.grid(row=2, column=1, sticky="w", **padding)

        # Target time
        ctk.CTkLabel(self.main_frame, text="Target time (HH:MM:SS.mmm):").grid(
            row=3, column=0, sticky="e", **padding
        )
        self.time_entry = ctk.CTkEntry(self.main_frame, width=260)
        self.time_entry.insert(0, "14:00:00.500")
        self.time_entry.grid(row=3, column=1, sticky="w", **padding)

        # ADD CRNs
        ctk.CTkLabel(self.main_frame, text="ADD (ECRN) CRNs:").grid(
            row=4, column=0, sticky="e", **padding
        )
        self.add_entry = ctk.CTkEntry(self.main_frame, width=260)
        self.add_entry.grid(row=4, column=1, sticky="w", **padding)

        # DROP CRNs
        ctk.CTkLabel(self.main_frame, text="DROP (SCRN) CRNs:").grid(
            row=5, column=0, sticky="e", **padding
        )
        self.drop_entry = ctk.CTkEntry(self.main_frame, width=260)
        self.drop_entry.grid(row=5, column=1, sticky="w", **padding)

        # Action buttons
        self.start_button = ctk.CTkButton(
            self.main_frame, text="Start scheduled enrollment", command=self.on_start
        )
        self.start_button.grid(row=6, column=0, columnspan=2, pady=(8, 12))

        # Log area
        self.log_text = ctk.CTkTextbox(self.main_frame, height=220, width=620)
        self.log_text.grid(row=7, column=0, columnspan=2, padx=8, pady=(4, 0), sticky="nsew")
        self.main_frame.grid_rowconfigure(7, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)

        # Footer
        footer = ctk.CTkLabel(
            self.main_frame,
            text="Note: use for personal purposes only and respect ITU OBS policies.",
            font=ctk.CTkFont(size=10),
        )
        footer.grid(row=8, column=0, columnspan=2, pady=(6, 0))

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.update_idletasks()

    def on_start(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        target_time = self.time_entry.get().strip()
        add_crns = parse_crns(self.add_entry.get().strip())
        drop_crns = parse_crns(self.drop_entry.get().strip())

        if not username or not password:
            self.log("Error: username and password are required.")
            return
        if not add_crns and not drop_crns:
            self.log("Error: you must provide at least one ADD or DROP CRN.")
            return
        if not target_time:
            self.log("Error: target time is required.")
            return

        self.start_button.configure(state="disabled")
        self.log("Starting scheduled enrollment in background...")

        thread = threading.Thread(
            target=self._run_enrollment,
            args=(username, password, target_time, add_crns, drop_crns),
            daemon=True,
        )
        thread.start()

    def _run_enrollment(
        self,
        username: str,
        password: str,
        target_time: str,
        add_crns: List[str],
        drop_crns: List[str],
    ) -> None:
        try:
            self.log("Logging into OBS to fetch JWT...")
            token: Optional[str] = get_jwt(username=username, password=password, headless=False)
            if not token:
                self.log("Failed to obtain JWT. Aborting.")
                return

            session = requests.Session()
            session.headers.update(default_headers())

            self.log(f"Waiting until {target_time}...")
            wait_until(target_time)

            headers = default_headers()
            headers["Authorization"] = f"Bearer {token}"
            body = {"ECRN": add_crns, "SCRN": drop_crns}

            self.log("Sending enrollment request...")
            resp = session.post(DERS_KAYIT_URL, json=body, headers=headers, timeout=30)
            self.log(f"Status: {resp.status_code}")
            self.log(f"Headers: {dict(resp.headers)}")
            self.log(f"Body: {resp.text}")

        except Exception as exc:
            self.log(f"Unexpected error: {exc}")
        finally:
            self.start_button.configure(state="normal")


def main() -> None:
    app = EnrollApp()
    app.mainloop()


if __name__ == "__main__":
    main()

