"""Small native launcher; camera work runs in a separate, gracefully stoppable process."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .calibration import load_profile, profile_filename
from .history import generate_dashboard, load_history
from .paths import data_directory, workout_directories
from .tempo import TempoTarget


def command(arguments: list[str]) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / "desktop.py"), *arguments]


class Launcher:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.root, self.tk = root, tk
        self.process = self.output = None
        self.closing = False
        self.stop_file = data_directory() / "workout-stop.txt"
        self.preferences = data_directory() / "preferences.json"
        root.title("Push / Up — Personal Training")
        root.geometry("980x710")
        root.minsize(900, 680)
        root.configure(bg="#f5f8f8")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.profile = tk.StringVar(value="default")
        self.variant = tk.StringVar(value="standard")
        self.camera = tk.StringVar(value="0")
        self.tempo = tk.StringVar(value="")
        self.goal = tk.StringVar(value="20")
        self.voice = tk.BooleanVar(value=True)
        try:
            saved = json.loads(self.preferences.read_text(encoding="utf-8"))
            for key in ("profile", "variant", "camera", "tempo", "goal", "voice"):
                if key in saved:
                    getattr(self, key).set(saved[key])
        except (OSError, ValueError, TypeError, tk.TclError):
            pass
        sidebar = tk.Frame(root, bg="#112d34", width=205)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar, text="PUSH / UP", bg="#112d34", fg="#7ce0bc", font=("Segoe UI", 23, "bold")
        ).pack(anchor="w", padx=22, pady=(34, 3))
        tk.Label(
            sidebar, text="PERSONAL TRAINING · V2", bg="#112d34", fg="#9bb6b8", font=("Segoe UI", 8)
        ).pack(anchor="w", padx=24)
        for text, handler in (
            ("Workout history", self.history),
            ("Open data folder", self.open_folder),
        ):
            tk.Button(
                sidebar,
                text=text,
                command=handler,
                bg="#25454b",
                fg="white",
                activebackground="#345b61",
                activeforeground="white",
                relief="flat",
                cursor="hand2",
                font=("Segoe UI", 10),
                pady=10,
            ).pack(fill="x", padx=20, pady=(40 if text == "Workout history" else 10, 0))
        tk.Label(
            sidebar,
            text="LOCAL BY DESIGN\n\nYour camera and workout\nrecords stay on your PC.",
            bg="#112d34",
            fg="#adc4c5",
            justify="left",
            font=("Segoe UI", 9),
        ).pack(side="bottom", anchor="w", padx=24, pady=30)
        main = tk.Frame(root, bg="#f5f8f8")
        main.pack(side="left", fill="both", expand=True, padx=32, pady=30)
        tk.Label(
            main,
            text="READY WHEN YOU ARE",
            bg="#f5f8f8",
            fg="#117d67",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            main,
            text="Make every rep count.",
            bg="#f5f8f8",
            fg="#142a33",
            font=("Segoe UI", 25, "bold"),
        ).pack(anchor="w", pady=(8, 2))
        tk.Label(
            main,
            text="Calibrate your view. Set your rhythm. Track your progress.",
            bg="#f5f8f8",
            fg="#63757e",
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        stats = tk.Frame(main, bg="#f5f8f8")
        stats.pack(fill="x", pady=23)
        self.total, self.best = tk.StringVar(value="0"), tk.StringVar(value="0")
        for index, (label, value) in enumerate(
            (("TOTAL REPS", self.total), ("BEST WORKOUT", self.best))
        ):
            card = tk.Frame(stats, bg="white", highlightbackground="#e2e9eb", highlightthickness=1)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 12 if index == 0 else 0))
            stats.grid_columnconfigure(index, weight=1)
            tk.Label(card, text=label, fg="#63757e", bg="white", font=("Segoe UI", 9)).pack(
                anchor="w", padx=18, pady=(13, 0)
            )
            tk.Label(
                card, textvariable=value, fg="#142a33", bg="white", font=("Segoe UI", 26, "bold")
            ).pack(anchor="w", padx=18, pady=(1, 12))
        settings = tk.Frame(main, bg="white", highlightbackground="#e2e9eb", highlightthickness=1)
        settings.pack(fill="x")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", padding=7)
        fields = [
            ("Profile", self.profile),
            ("Variant", self.variant),
            ("Camera index", self.camera),
            ("Rep goal", self.goal),
            ("Tempo · lower-hold-rise", self.tempo),
        ]
        for index, (label, variable) in enumerate(fields):
            row, col = divmod(index, 2)
            cell = tk.Frame(settings, bg="white")
            cell.grid(row=row, column=col, sticky="ew", padx=16, pady=(12, 0))
            settings.grid_columnconfigure(col, weight=1)
            tk.Label(cell, text=label, bg="white", fg="#63757e", font=("Segoe UI", 9)).pack(
                anchor="w"
            )
            if variable is self.variant:
                widget = ttk.Combobox(
                    cell,
                    textvariable=variable,
                    values=("standard", "knee"),
                    state="readonly",
                    width=23,
                )
            else:
                widget = tk.Entry(
                    cell,
                    textvariable=variable,
                    bg="#f5f8f8",
                    fg="#142a33",
                    relief="flat",
                    font=("Segoe UI", 11),
                )
            widget.pack(fill="x", ipady=7, pady=(4, 0))
        tk.Checkbutton(
            settings,
            text="Spoken coaching · offline",
            variable=self.voice,
            bg="white",
            activebackground="white",
            fg="#142a33",
            font=("Segoe UI", 10),
            anchor="w",
        ).grid(row=2, column=1, sticky="ew", padx=16, pady=(26, 0))
        self.profile_text = tk.StringVar()
        tk.Label(
            settings,
            textvariable=self.profile_text,
            bg="white",
            fg="#63757e",
            font=("Segoe UI", 8),
            anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=13)
        actions = tk.Frame(main, bg="#f5f8f8")
        actions.pack(fill="x", pady=(20, 0))
        self.action_buttons = []
        for index, (text, action) in enumerate(
            (
                ("Start workout", lambda: self.start()),
                ("Calibrate profile", lambda: self.start("calibrate")),
                ("Try demo", lambda: self.start("demo")),
                ("Analyze video", self.video),
            )
        ):
            button = tk.Button(
                actions,
                text=text,
                command=action,
                relief="flat",
                cursor="hand2",
                bg="#117d67" if index == 0 else "#e3edeb",
                fg="white" if index == 0 else "#142a33",
                font=("Segoe UI", 10, "bold"),
                pady=11,
            )
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 8), pady=(0, 8))
            actions.grid_columnconfigure(index % 2, weight=1)
            self.action_buttons.append(button)
        self.status = tk.StringVar(
            value="Place the camera to your side with your full body in view."
        )
        tk.Label(
            main,
            textvariable=self.status,
            fg="#63757e",
            bg="#f5f8f8",
            font=("Segoe UI", 9),
            wraplength=590,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        self.stop_button = tk.Button(
            main,
            text="Finish and save",
            command=self.stop,
            state="disabled",
            relief="flat",
            bg="#f5f8f8",
            fg="#117d67",
            font=("Segoe UI", 9, "bold"),
        )
        self.stop_button.pack(anchor="w", pady=(5, 0))
        self.profile.trace_add("write", lambda *args: self.refresh_profile())
        self.variant.trace_add("write", lambda *args: self.variant_changed())
        self.refresh()
        root.after(300, self.poll)

    def variant_changed(self):
        if self.profile.get() == "default" and self.variant.get() == "knee":
            self.profile.set("knee")
        elif self.profile.get() == "knee" and self.variant.get() == "standard":
            self.profile.set("default")
        self.refresh_profile()

    def refresh_profile(self):
        try:
            profile = load_profile(data_directory() / "profiles", self.profile.get())
            self.profile_text.set(
                f"Saved {profile.variant} profile: top {profile.up_angle:.0f}°, bottom "
                f"{profile.down_angle:.0f}°"
                if profile
                else "No saved calibration · defaults will be used"
            )
        except (ValueError, OSError):
            self.profile_text.set("Choose a valid profile name or recalibrate this profile")

    def refresh(self):
        sessions = [s for s in load_history(workout_directories())["sessions"] if not s["demo"]]
        self.total.set(str(sum(s["reps"] for s in sessions)))
        self.best.set(str(max((s["reps"] for s in sessions), default=0)))
        self.refresh_profile()

    def options(self):
        profile_filename(self.profile.get())
        camera, goal = int(self.camera.get()), int(self.goal.get())
        if camera < 0 or goal <= 0 or self.variant.get() not in ("standard", "knee"):
            raise ValueError(
                "Use a non-negative camera index, a positive rep goal and a valid variant."
            )
        if self.tempo.get().strip():
            TempoTarget.parse(self.tempo.get().strip())
        return [
            "--variant",
            self.variant.get(),
            "--profile",
            self.profile.get(),
            "--goal",
            str(goal),
            "--data-dir",
            str(data_directory()),
            "--stop-file",
            str(self.stop_file),
            *(["--tempo", self.tempo.get().strip()] if self.tempo.get().strip() else []),
            *(["--voice"] if self.voice.get() else []),
        ]

    def start(self, mode="workout", video=None):
        from tkinter import messagebox

        if self.process:
            return
        try:
            arguments = self.options()
            if mode == "demo":
                arguments += ["--demo"]
            elif video:
                arguments += ["--video", str(video)]
            else:
                arguments += ["--camera", str(int(self.camera.get()))]
            if mode == "calibrate":
                arguments += ["--calibrate"]
            data_directory().mkdir(parents=True, exist_ok=True)
            self.stop_file.unlink(missing_ok=True)
            self.preferences.write_text(
                json.dumps(
                    {
                        key: getattr(self, key).get()
                        for key in ("profile", "variant", "camera", "tempo", "goal", "voice")
                    }
                ),
                encoding="utf-8",
            )
            self.output = (data_directory() / "last_run.log").open("w", encoding="utf-8")
            self.process = subprocess.Popen(
                command(arguments),
                stdout=self.output,
                stderr=self.output,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for button in self.action_buttons:
                button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.status.set(
                "Calibration: hold the top, then the bottom for 2 seconds each."
                if (mode == "calibrate")
                else "Workout open · press Q in the camera window, or Finish and save here."
            )
        except (ValueError, OSError) as exc:
            if self.output:
                self.output.close()
            messagebox.showerror("Cannot start", str(exc), parent=self.root)

    def poll(self):
        from tkinter import messagebox

        if self.process and self.process.poll() is not None:
            result = self.process.returncode
            self.process = None
            if self.output:
                self.output.close()
                self.output = None
            self.stop_file.unlink(missing_ok=True)
            self.stop_button.configure(state="disabled")
            for button in self.action_buttons:
                button.configure(state="normal")
            self.refresh()
            self.status.set(
                "Finished · open Workout history to see completed sessions."
                if result == 0
                else "Calibration cancelled."
                if result == 2
                else "Run ended with an error."
            )
            if result not in (0, 2) and not self.closing:
                messagebox.showerror(
                    "Run ended",
                    (data_directory() / "last_run.log").read_text(
                        encoding="utf-8", errors="replace"
                    )[-2000:],
                    parent=self.root,
                )
        if self.closing and not self.process:
            self.root.destroy()
            return
        self.root.after(300, self.poll)

    def stop(self):
        if self.process:
            self.stop_file.write_text("stop", encoding="utf-8")
            self.status.set("Finishing the current frame and saving your session…")

    def close(self):
        self.closing = True
        if self.process:
            self.stop()
        else:
            self.root.destroy()

    def history(self):
        from tkinter import messagebox

        try:
            generate_dashboard()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot open history", str(exc), parent=self.root)

    def video(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a workout video",
            filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")],
        )
        if path:
            self.start(video=Path(path))

    def open_folder(self):
        import webbrowser

        data_directory().mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(data_directory())
        else:
            webbrowser.open(data_directory().as_uri())


def launch(smoke=False) -> int:
    import tkinter as tk

    root = tk.Tk()
    Launcher(root)
    if smoke:
        root.update_idletasks()
        assert root.winfo_width() >= 900
        root.after(300, root.destroy)
    root.mainloop()
    return 0


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if getattr(sys, "frozen", False):
        for name in ("stdout", "stderr"):
            if getattr(sys, name) is None:
                data_directory().mkdir(parents=True, exist_ok=True)
                filename = "last_run.log" if arguments else "runtime.log"
                setattr(sys, name, (data_directory() / filename).open("a", encoding="utf-8"))
    if arguments == ["--desktop-smoke"]:
        return launch(smoke=True)
    if arguments:
        from .app import main as cli

        return cli(arguments)
    return launch()
