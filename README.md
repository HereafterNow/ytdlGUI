# yt-dlp GUI

A small Windows desktop wrapper around [yt-dlp](https://github.com/yt-dlp/yt-dlp) with:

- URL field
- Download location picker (with Browse button)
- Resolution selector (Best, 4K, 1440p, 1080p, 720p, 480p, 360p)
- Video / Video-only / Audio-only (MP3) mode

## Setup (one time)

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/) — check
   **"Add python.exe to PATH"** during install (this build of Python includes Tkinter,
   which the GUI is built on).
2. Open a terminal in this folder and install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. **ffmpeg** is needed to merge video+audio and to extract MP3 audio.
   Either:
   - `winget install ffmpeg` (installs it system-wide, needs a PATH refresh/restart), or
   - it's already covered — `imageio-ffmpeg` in requirements.txt bundles a working
     copy automatically, so you can usually skip a manual ffmpeg install entirely.

## Running it

Double-click `run.bat`, or from a terminal:

```
python ytdlp_gui.py
```

## Turning it into a standalone .exe (optional)

```
pip install pyinstaller
pyinstaller --onefile --windowed ytdlp_gui.py
```

The .exe will be in the `dist` folder.

## Notes

- "Video" downloads and merges the best video+audio into one MP4.
- "Video only" downloads just the video stream, no audio track.
- "Audio only" extracts a 192kbps MP3.
- Only use this on content you have the right to download (your own uploads,
  Creative Commons material, or anything permitted by the site's terms).
