import tkinter as tk
from tkinter import ttk, filedialog
import subprocess
import threading
import shutil
import queue
import re
import os
import json

RESOLUTIONS = [
    ("Max", None),
    ("2160p (4K)", 2160),
    ("1440p (2K)", 1440),
    ("1080p", 1080),
    ("720p", 720),
    ("480p", 480),
    ("360p", 360),
    ("240p", 240),
    ("144p", 144),
]

PROGRESS_RE = re.compile(r"\[download\]\s+(\d+\.?\d*)%")

# Config location: C:\Users\Trung\AppData\Roaming\ytdlp_gui.json
CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", r"C:\Users\Trung\AppData\Roaming"),
    "ytdlp_gui.json",
)

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_config(data):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass

def build_format(height, video_only):
    if video_only:
        if height is None:
            return "bv*/b"
        return f"bv*[height<={height}]/b[height<={height}]/b"
    if height is None:
        return "bv*+ba/b"
    return f"bv*[height<={height}]+ba/b[height<={height}]/b"

def resolve_ytdlp(folder):
    """Return the yt-dlp executable to use, or None."""
    if folder:
        folder = folder.strip().strip('"')
        for name in ("yt-dlp.exe", "yt-dlp"):
            candidate = os.path.join(folder, name)
            if os.path.isfile(candidate):
                return candidate
    return shutil.which("yt-dlp")

class DownloaderApp:
    def __init__(self, root):
        self.root = root
        root.title("yt-dlp GUI")
        root.geometry("860x780")

        self.job_queue = queue.Queue()
        self.worker_thread = None
        self.current_proc = None
        self.cancel_flag = threading.Event()
        self.update_running = False

        self.config = load_config()
        self._build_ui()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------
    def _build_ui(self):
        root = self.root

        # yt-dlp folder (top)
        ytdlp_frame = tk.Frame(root)
        ytdlp_frame.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(ytdlp_frame, text="yt-dlp folder:").pack(side="left")
        self.ytdlp_folder_var = tk.StringVar(value=self.config.get("ytdlp_folder", ""))
        self.ytdlp_folder_var.trace_add("write", lambda *_: self._save_now())
        tk.Entry(ytdlp_frame, textvariable=self.ytdlp_folder_var).pack(
            side="left", fill="x", expand=True, padx=4
        )
        tk.Button(
            ytdlp_frame, text="Folder…",
            command=lambda: self.ytdlp_folder_var.set(
                filedialog.askdirectory() or self.ytdlp_folder_var.get()
            ),
        ).pack(side="left")
        tk.Label(ytdlp_frame, text="(blank = use PATH)", fg="gray").pack(
            side="left", padx=(6, 0)
        )

        # URL + Add to queue
        url_frame = tk.Frame(root)
        url_frame.pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(url_frame, text="URL:").pack(side="left")
        self.url_entry = tk.Entry(url_frame)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.url_entry.bind("<Return>", lambda e: self.add_to_queue())
        self.add_btn = tk.Button(url_frame, text="Add to queue", command=self.add_to_queue)
        self.add_btn.pack(side="left")

        # Output folder
        folder_frame = tk.Frame(root)
        folder_frame.pack(fill="x", padx=8, pady=4)
        tk.Label(folder_frame, text="Save to:").pack(side="left")
        self.folder_var = tk.StringVar(value=self.config.get("save_folder", ""))
        self.folder_var.trace_add("write", lambda *_: self._save_now())
        tk.Entry(folder_frame, textvariable=self.folder_var).pack(
            side="left", fill="x", expand=True, padx=4
        )
        tk.Button(
            folder_frame, text="Folder…",
            command=lambda: self.folder_var.set(
                filedialog.askdirectory() or self.folder_var.get()
            ),
        ).pack(side="left")

        # Options
        opts = tk.Frame(root)
        opts.pack(fill="x", padx=8, pady=4)

        tk.Label(opts, text="Max resolution:").pack(side="left")
        self.res_combo = ttk.Combobox(
            opts, values=[l for l, _ in RESOLUTIONS], state="readonly", width=14
        )
        self.res_combo.current(0)
        self.res_combo.pack(side="left", padx=(4, 16))

        self.merge_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="Merge to MP4", variable=self.merge_var).pack(
            side="left", padx=(0, 12)
        )

        self.audio_only_var = tk.BooleanVar(value=False)
        self.video_only_var = tk.BooleanVar(value=False)
        self.audio_only_var.trace_add("write", self._update_format_state)
        self.video_only_var.trace_add("write", self._update_format_state)

        tk.Checkbutton(opts, text="Audio only (MP3)", variable=self.audio_only_var).pack(
            side="left", padx=(0, 12)
        )
        tk.Checkbutton(opts, text="Video only (no audio)", variable=self.video_only_var).pack(
            side="left"
        )

        # Queue list + buttons
        q_frame = tk.LabelFrame(root, text="Queue")
        q_frame.pack(fill="both", expand=False, padx=8, pady=4)

        self.queue_list = tk.Listbox(q_frame, height=6)
        self.queue_list.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        sb = tk.Scrollbar(q_frame, orient="vertical", command=self.queue_list.yview)
        sb.pack(side="left", fill="y", pady=4)
        self.queue_list.config(yscrollcommand=sb.set)

        q_btns = tk.Frame(q_frame)
        q_btns.pack(side="left", fill="y", padx=4, pady=4)

        self.remove_btn = tk.Button(q_btns, text="Remove", command=self.remove_selected)
        self.remove_btn.pack(fill="x", pady=2)
        self.clear_btn = tk.Button(q_btns, text="Clear", command=self.clear_queue)
        self.clear_btn.pack(fill="x", pady=2)
        self.start_btn = tk.Button(q_btns, text="Start", command=self.start_queue)
        self.start_btn.pack(fill="x", pady=2)
        self.cancel_btn = tk.Button(q_btns, text="Cancel", command=self.cancel_current)
        self.cancel_btn.pack(fill="x", pady=2)

        tk.Frame(q_btns, height=8).pack(fill="x")
        self.update_btn = tk.Button(q_btns, text="Update yt-dlp (-U)", command=self.update_ytdlp)
        self.update_btn.pack(fill="x", pady=2)

        # Progress bar
        prog_frame = tk.Frame(root)
        prog_frame.pack(fill="x", padx=8, pady=(0, 4))
        self.progress = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_label = tk.Label(prog_frame, text="idle", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        # Log
        self.log = tk.Text(root, wrap="word", height=16)
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._update_format_state()

    def _update_format_state(self, *_):
        if self.audio_only_var.get():
            self.res_combo.config(state="disabled")
        else:
            self.res_combo.config(state="readonly")

        if self.audio_only_var.get() and self.video_only_var.get():
            self.video_only_var.set(False)

    # ---------- Config ----------
    def _save_now(self):
        save_config({
            "ytdlp_folder": self.ytdlp_folder_var.get().strip(),
            "save_folder": self.folder_var.get().strip(),
        })

    # ---------- Enable/disable groups ----------
    def _set_download_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for w in (self.add_btn, self.remove_btn, self.clear_btn,
                  self.start_btn, self.cancel_btn):
            w.config(state=state)

    def _set_update_enabled(self, enabled):
        self.update_btn.config(state="normal" if enabled else "disabled")

    # ---------- yt-dlp resolution ----------
    def _ytdlp_path(self):
        return resolve_ytdlp(self.ytdlp_folder_var.get()) or "yt-dlp"

    def _check_ytdlp(self):
        folder = self.ytdlp_folder_var.get().strip()
        path = resolve_ytdlp(folder)
        if path is None:
            if folder:
                self._log(
                    f"[warn] No yt-dlp.exe or yt-dlp found in:\n"
                    f"       {folder}\n"
                    f"       Falling back to 'yt-dlp' on PATH.\n\n"
                )
            else:
                self._log(
                    "[warn] yt-dlp not found on PATH. Set a yt-dlp folder above.\n\n"
                )
            return False
        return True

    # ---------- Queue management ----------
    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.queue_list.insert(tk.END, url)
        self.url_entry.delete(0, tk.END)

    def remove_selected(self):
        for i in reversed(self.queue_list.curselection()):
            self.queue_list.delete(i)

    def clear_queue(self):
        self.queue_list.delete(0, tk.END)

    def start_queue(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Queue already running.\n")
            return
        items = list(self.queue_list.get(0, tk.END))
        if not items:
            self._log("Queue is empty.\n")
            return

        self._check_ytdlp()

        self.clear_queue()
        for url in items:
            self.job_queue.put(url)
        self.cancel_flag.clear()

        self._set_update_enabled(False)

        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def cancel_current(self):
        self.cancel_flag.set()
        if self.current_proc and self.current_proc.poll() is None:
            self.current_proc.terminate()
            self._log("\n[cancel] terminating current download…\n")

    # ---------- Worker ----------
    def _worker(self):
        while not self.cancel_flag.is_set():
            try:
                url = self.job_queue.get_nowait()
            except queue.Empty:
                break
            self._run_one(url)
        self.root.after(0, lambda: self._set_progress(0, "idle"))
        self._log("\n[queue] done.\n")
        self.root.after(0, lambda: self._set_update_enabled(True))

    def _run_one(self, url):
        ytdlp = self._ytdlp_path()
        out_dir = self.folder_var.get().strip() or "."
        outtmpl = os.path.join(out_dir, "%(title)s.%(ext)s")

        label, height = RESOLUTIONS[self.res_combo.current()]
        audio_only = self.audio_only_var.get()
        video_only = self.video_only_var.get()

        if audio_only:
            cmd = [ytdlp, "-x", "--audio-format", "mp3", "-o", outtmpl]
        else:
            fmt = build_format(height, video_only)
            cmd = [ytdlp, "-f", fmt, "-o", outtmpl]
            if self.merge_var.get() and not video_only:
                cmd += ["--merge-output-format", "mp4"]

        cmd += ["--newline", url]

        self._log(f"\n$ {' '.join(cmd)}\n\n")
        self.root.after(0, lambda: self._set_progress(0, "0%"))

        try:
            self.current_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            self._log(f"[error] yt-dlp not found: {ytdlp}\n")
            return

        assert self.current_proc.stdout is not None
        for line in self.current_proc.stdout:
            self._log(line)
            m = PROGRESS_RE.search(line)
            if m:
                pct = float(m.group(1))
                self.root.after(0, lambda p=pct: self._set_progress(p, f"{p:.0f}%"))

        self.current_proc.wait()
        code = self.current_proc.returncode
        self._log(f"\n[done] exit code {code}\n")
        self.current_proc = None

    # ---------- Update ----------
    def update_ytdlp(self):
        if self.update_running:
            return
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("[update] downloads are running; cancel them first.\n")
            return

        if not self._check_ytdlp():
            self._log("[update] aborting — set a valid yt-dlp folder or fix PATH.\n")
            return

        ytdlp = self._ytdlp_path()
        cmd = [ytdlp, "-U"]

        self._log(f"\n$ {' '.join(cmd)}\n\n")
        self.update_running = True

        self._set_download_controls_enabled(False)
        self._set_update_enabled(False)

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in proc.stdout:
                    self._log(line)
                proc.wait()
                self._log(f"\n[update] exit code {proc.returncode}\n")
            except FileNotFoundError:
                self._log(f"[error] command not found: {cmd[0]}\n")
            finally:
                self.update_running = False
                self.root.after(0, lambda: self._set_download_controls_enabled(True))
                self.root.after(0, lambda: self._set_update_enabled(True))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Thread-safe UI helpers ----------
    def _log(self, text):
        self.root.after(0, lambda: self._append_log(text))

    def _append_log(self, text):
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def _set_progress(self, pct, label):
        self.progress["value"] = pct
        self.progress_label.config(text=label)

    # ---------- Lifecycle ----------
    def _on_close(self):
        self._save_now()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = DownloaderApp(root)
    root.mainloop()