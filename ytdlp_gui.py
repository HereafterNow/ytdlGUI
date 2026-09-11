"""
yt-dlp GUI — a simple Windows 11-styled desktop wrapper around yt-dlp.

Features:
  - URL input
  - Download location picker
  - Resolution selector
  - Video / Video-only / Audio-only mode (radio buttons)
  - Live progress bar + log

Requirements (install once):
    pip install -r requirements.txt

ffmpeg is required to merge separate video+audio streams and to extract
audio to mp3. If ffmpeg isn't on your PATH, this app will fall back to
the bundled binary from the optional `imageio-ffmpeg` package.
"""

import os
import sys
import shutil
import subprocess
import threading
import queue
from pathlib import Path

# When frozen into a PyInstaller --onefile exe, customtkinter's theme/font
# assets are unpacked into a temp folder (sys._MEIPASS) at startup, and some
# versions of customtkinter resolve those assets relative to the current
# working directory. Switching into that folder before importing it avoids
# a FileNotFoundError for the theme .json file. This block is a no-op when
# running as a plain .py script (sys.frozen is only set inside a build).
if getattr(sys, "frozen", False):
    os.chdir(sys._MEIPASS)

import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


def find_ffmpeg():
    """Look for ffmpeg on PATH, then fall back to imageio-ffmpeg's bundled binary."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


RESOLUTIONS = {
    "Best available": None,
    "2160p (4K)": 2160,
    "1440p (2K)": 1440,
    "1080p (Full HD)": 1080,
    "720p (HD)": 720,
    "480p": 480,
    "360p": 360,
}


class YTDLApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("yt-dlp GUI")
        self.geometry("640x620")
        self.minsize(600, 580)

        ctk.set_appearance_mode("System")   # follows Windows 11 light/dark mode
        ctk.set_default_color_theme("blue")

        self.ffmpeg_path = find_ffmpeg()
        self.download_thread = None
        self.update_thread = None
        self.ui_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._poll_ui_queue)

    # ---------------------------------------------------------------- UI --
    def _build_ui(self):
        pad = {"padx": 16, "pady": 8}

        ctk.CTkLabel(
            self, text="yt-dlp Downloader", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", padx=16, pady=(16, 0))

        # --- URL -----------------------------------------------------
        url_frame = ctk.CTkFrame(self, fg_color="transparent")
        url_frame.pack(fill="x", **pad)
        ctk.CTkLabel(url_frame, text="Video URL", anchor="w").pack(fill="x")
        self.url_entry = ctk.CTkEntry(
            url_frame, placeholder_text="https://www.youtube.com/watch?v=..."
        )
        self.url_entry.pack(fill="x", pady=(4, 0))

        # --- Download location ---------------------------------------
        loc_frame = ctk.CTkFrame(self, fg_color="transparent")
        loc_frame.pack(fill="x", **pad)
        ctk.CTkLabel(loc_frame, text="Download location", anchor="w").pack(fill="x")
        loc_row = ctk.CTkFrame(loc_frame, fg_color="transparent")
        loc_row.pack(fill="x", pady=(4, 0))
        self.location_var = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.location_entry = ctk.CTkEntry(loc_row, textvariable=self.location_var)
        self.location_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(loc_row, text="Browse...", width=90, command=self._browse).pack(
            side="left", padx=(8, 0)
        )

        # --- Resolution + mode ----------------------------------------
        opts_frame = ctk.CTkFrame(self, fg_color="transparent")
        opts_frame.pack(fill="x", **pad)

        res_col = ctk.CTkFrame(opts_frame, fg_color="transparent")
        res_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(res_col, text="Resolution", anchor="w").pack(fill="x")
        self.resolution_var = ctk.StringVar(value="1080p (Full HD)")
        ctk.CTkOptionMenu(
            res_col, values=list(RESOLUTIONS.keys()), variable=self.resolution_var
        ).pack(fill="x", pady=(4, 0))

        mode_col = ctk.CTkFrame(opts_frame, fg_color="transparent")
        mode_col.pack(side="left", fill="both", expand=True, padx=(16, 0))
        ctk.CTkLabel(mode_col, text="Download as", anchor="w").pack(fill="x")
        self.mode_var = ctk.StringVar(value="video")
        ctk.CTkRadioButton(
            mode_col, text="Video (with audio)", variable=self.mode_var, value="video"
        ).pack(anchor="w", pady=(4, 0))
        ctk.CTkRadioButton(
            mode_col,
            text="Video only (no audio)",
            variable=self.mode_var,
            value="video_only",
        ).pack(anchor="w", pady=(4, 0))
        ctk.CTkRadioButton(
            mode_col, text="Audio only (MP3)", variable=self.mode_var, value="audio"
        ).pack(anchor="w", pady=(4, 0))

        # --- Progress ---------------------------------------------------
        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.pack(fill="x", **pad)
        self.progress_bar = ctk.CTkProgressBar(prog_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x")
        self.status_label = ctk.CTkLabel(prog_frame, text="Idle", anchor="w")
        self.status_label.pack(fill="x", pady=(4, 0))

        # --- Log ----------------------------------------------------------
        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, **pad)
        ctk.CTkLabel(log_frame, text="Log", anchor="w").pack(fill="x")
        self.log_box = ctk.CTkTextbox(log_frame, height=140)
        self.log_box.pack(fill="both", expand=True, pady=(4, 0))
        self.log_box.configure(state="disabled")

        # --- Download button -----------------------------------------
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", **pad)
        self.download_btn = ctk.CTkButton(
            btn_frame, text="Download", height=36, command=self._start_download
        )
        self.download_btn.pack(fill="x")

        # --- yt-dlp version / update -----------------------------------
        version_frame = ctk.CTkFrame(self, fg_color="transparent")
        version_frame.pack(fill="x", padx=16, pady=(0, 12))
        self.version_label = ctk.CTkLabel(
            version_frame,
            text=self._current_ytdlp_version(),
            text_color=("gray40", "gray60"),
        )
        self.version_label.pack(side="left")
        self.update_btn = ctk.CTkButton(
            version_frame,
            text="Check for yt-dlp update",
            width=180,
            height=26,
            fg_color="transparent",
            border_width=1,
            command=self._start_update,
        )
        self.update_btn.pack(side="right")

        if yt_dlp is None:
            self._log("yt-dlp is not installed. Run: pip install -r requirements.txt")
        if self.ffmpeg_path is None:
            self._log("Warning: ffmpeg not found. Merging video+audio and MP3 extraction need it.")
            self._log("Install with: winget install ffmpeg   (or) pip install imageio-ffmpeg")

    # ------------------------------------------------------------ helpers --
    def _current_ytdlp_version(self):
        if yt_dlp is None:
            return "yt-dlp: not installed"
        try:
            return f"yt-dlp v{yt_dlp.version.__version__}"
        except Exception:
            return "yt-dlp: version unknown"

    def _browse(self):
        chosen = filedialog.askdirectory(
            initialdir=self.location_var.get() or str(Path.home())
        )
        if chosen:
            self.location_var.set(chosen)

    def _log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll_ui_queue(self):
        """Runs on the main thread only — safe place to touch widgets."""
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    frac, status = payload
                    self.progress_bar.set(max(0.0, min(1.0, frac)))
                    if status:
                        self.status_label.configure(text=status)
                elif kind == "done":
                    self.download_btn.configure(state="normal", text="Download")
                    messagebox.showinfo("Done", "Download completed successfully.")
                elif kind == "error":
                    self.download_btn.configure(state="normal", text="Download")
                    messagebox.showerror("Download failed", payload)
                elif kind == "update_done":
                    self.update_btn.configure(state="normal", text="Check for yt-dlp update")
                    self.version_label.configure(text=self._current_ytdlp_version())
                    messagebox.showinfo(
                        "Update finished",
                        "pip has finished updating yt-dlp.\n"
                        "Restart this app for the new version to take effect "
                        "(the copy already running stays loaded in memory until then).",
                    )
                elif kind == "update_error":
                    self.update_btn.configure(state="normal", text="Check for yt-dlp update")
                    messagebox.showerror("Update failed", payload)
        except queue.Empty:
            pass
        self.after(150, self._poll_ui_queue)

    # ------------------------------------------------------- download logic --
    def _start_download(self):
        if yt_dlp is None:
            messagebox.showerror(
                "Missing dependency", "yt-dlp is not installed.\nRun: pip install yt-dlp"
            )
            return
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showinfo("Busy", "A download is already in progress.")
            return
        if self.update_thread and self.update_thread.is_alive():
            messagebox.showinfo("Busy", "Wait for the yt-dlp update to finish first.")
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a video URL first.")
            return

        out_dir = self.location_var.get().strip() or str(Path.home() / "Downloads")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        mode = self.mode_var.get()
        if mode == "audio" and self.ffmpeg_path is None:
            messagebox.showwarning(
                "ffmpeg required",
                "Audio extraction needs ffmpeg.\n"
                "Install it (winget install ffmpeg) or run: pip install imageio-ffmpeg",
            )
            return

        height = RESOLUTIONS[self.resolution_var.get()]
        self.download_btn.configure(state="disabled", text="Downloading...")
        self.progress_bar.set(0)
        self.status_label.configure(text="Starting...")

        self.download_thread = threading.Thread(
            target=self._run_download, args=(url, out_dir, mode, height), daemon=True
        )
        self.download_thread.start()

    def _run_download(self, url, out_dir, mode, height):
        """Runs in a background thread. Only ever pushes to ui_queue —
        never touches Tkinter widgets directly (Tkinter is not thread-safe)."""
        try:
            ydl_opts = {
                "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                "progress_hooks": [self._progress_hook],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }
            if self.ffmpeg_path:
                ydl_opts["ffmpeg_location"] = self.ffmpeg_path

            height_filter = f"[height<={height}]" if height else ""

            if mode == "video":
                ydl_opts["format"] = f"bestvideo{height_filter}+bestaudio/best{height_filter}"
                ydl_opts["merge_output_format"] = "mp4"
            elif mode == "video_only":
                ydl_opts["format"] = f"bestvideo{height_filter}"
            elif mode == "audio":
                ydl_opts["format"] = "bestaudio/best"
                ydl_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ]

            self.ui_queue.put(("log", f"Downloading: {url}"))
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            self.ui_queue.put(("log", "Done."))
            self.ui_queue.put(("progress", (1.0, "Completed")))
            self.ui_queue.put(("done", None))
        except Exception as e:
            self.ui_queue.put(("log", f"Error: {e}"))
            self.ui_queue.put(("progress", (0, "Failed")))
            self.ui_queue.put(("error", str(e)))

    def _progress_hook(self, d):
        """Called by yt-dlp from the background thread — must only queue, not draw."""
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            frac = downloaded / total if total else 0
            pct = f"{frac * 100:.1f}%" if total else "..."
            speed = d.get("speed")
            speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "-"
            self.ui_queue.put(("progress", (frac, f"Downloading {pct} @ {speed_str}")))
        elif status == "finished":
            self.ui_queue.put(("progress", (1.0, "Processing (merging/converting)...")))
            self.ui_queue.put(("log", "Download finished, post-processing..."))

    # --------------------------------------------------------- update logic --
    def _start_update(self):
        """Runs only when the button is clicked — nothing here updates automatically."""
        if getattr(sys, "frozen", False):
            messagebox.showinfo(
                "Not available in this build",
                "This packaged .exe doesn't carry pip or a live Python install "
                "with it, so it can't update yt-dlp in place.\n\n"
                "To get a newer yt-dlp: run ytdlp_gui.py directly with Python "
                "installed (where this button works normally), or rebuild the "
                ".exe after running 'pip install --upgrade yt-dlp' yourself.",
            )
            return
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showinfo("Busy", "Wait for the current download to finish first.")
            return
        if self.update_thread and self.update_thread.is_alive():
            return

        self.update_btn.configure(state="disabled", text="Updating...")
        self._log("Checking for a newer yt-dlp release...")

        self.update_thread = threading.Thread(target=self._run_update, daemon=True)
        self.update_thread.start()

    def _run_update(self):
        """Runs in a background thread. Only ever pushes to ui_queue (see _run_download)."""
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.ui_queue.put(("log", line))
            proc.wait()

            if proc.returncode == 0:
                self.ui_queue.put(("update_done", None))
            else:
                self.ui_queue.put(("update_error", f"pip exited with code {proc.returncode}"))
        except Exception as e:
            self.ui_queue.put(("update_error", str(e)))


if __name__ == "__main__":
    app = YTDLApp()
    app.mainloop()
