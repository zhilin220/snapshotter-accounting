"""SnapShotter — screenshot capture with accounting evidence organization.

Windows desktop utility. Captures are ordinary PNG files; an accompanying CSV
index records the user-entered workpaper context. The index is an organizer,
not a tamper-proof audit log.
"""
from __future__ import annotations

import csv
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def _ensure_packages() -> None:
    """If mss/Pillow are missing, offer to install them into the Python running this script.

    Works the same from PyCharm, VS Code, IDLE or a command prompt; no .bat file or
    admin rights needed (outside a virtual environment it installs with --user).
    """
    try:
        import mss  # noqa: F401
        import PIL  # noqa: F401
        return
    except ImportError:
        pass

    req = Path(__file__).with_name("requirements.txt")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    cmd = [sys.executable, "-m", "pip", "install"] + ([] if in_venv else ["--user"])
    cmd += ["-r", str(req)] if req.exists() else ["mss>=9.0.1", "Pillow>=10.0.0"]
    manual = f'"{sys.executable}" -m pip install {"" if in_venv else "--user "}-r requirements.txt'

    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(
            "SnapShotter: one-time setup",
            "SnapShotter needs two free packages (mss and Pillow) that aren't installed "
            f"for this Python yet:\n\n{sys.executable}\n\n"
            "Install them now? It takes under a minute and doesn't need admin rights.",
            parent=root):
        root.destroy()
        raise SystemExit(f"SnapShotter needs mss and Pillow. Install them with:\n  {manual}")

    note = tk.Toplevel(root)
    note.title("SnapShotter")
    note.resizable(False, False)
    tk.Label(note, text="Installing mss and Pillow…\nThis window closes when it's done.",
             font=("Segoe UI", 10), padx=30, pady=22).pack()
    note.update()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                cwd=str(Path(__file__).parent))
        ok, output = result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    except Exception as exc:  # pip missing, timeout, etc.
        ok, output = False, str(exc)
    note.destroy()

    if ok:
        import importlib
        import site
        user_site = site.getusersitepackages()
        if not in_venv and user_site not in sys.path:
            sys.path.append(user_site)  # a fresh --user folder isn't on the path yet
        importlib.invalidate_caches()
        try:
            import mss  # noqa: F401,F811
            import PIL  # noqa: F401,F811
            root.destroy()
            return
        except ImportError as exc:
            output += f"\n{exc}"

    tail = "\n".join(output.strip().splitlines()[-8:])
    hint = ""
    if any(s in output for s in ("SSL", "ProxyError", "ConnectTimeout", "NewConnectionError", "Max retries", "from versions: none")):
        hint = ("\n\nThis looks like your network blocking the Python package site. "
                "Ask IT for the company proxy or package mirror, or set PyCharm's HTTP proxy.")
    messagebox.showerror("SnapShotter: setup failed",
                         f"Couldn't install the packages.{hint}\n\nYou can try this yourself "
                         f"(e.g. in PyCharm's Terminal tab):\n{manual}\n\nLast output:\n{tail}",
                         parent=root)
    root.destroy()
    raise SystemExit(1)


_ensure_packages()
import mss  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageTk  # noqa: E402

# mss 10+ provides mss.MSS (and deprecates mss.mss); mss 9 only has mss.mss.
_new_mss = getattr(mss, "MSS", None) or mss.mss

APP_NAME = "SnapShotter"
DEFAULT_FOLDER = Path.home() / "Documents" / "Accounting Evidence"
SETTINGS_PATH = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME / "settings.json"
CAPTURE_MODES = [
    ("region", "Rectangular area", "Select any area — just like Snipping Tool"),
    ("screen", "All screens together", "One image spanning your desktop"),
    ("monitor", "One monitor", "Choose a specific display"),
    ("separate", "Each monitor separately", "One image per display"),
]
MODE_TILES = [
    ("region", "⬚", "Area", "Drag to select, like Snipping Tool"),
    ("monitor", "▭", "One screen", "Pick a display"),
    ("screen", "⧉", "All screens", "Whole desktop, one image"),
    ("separate", "⊞", "Each screen", "One image per display"),
]
BG = "#f4f6fa"
CARD = "#ffffff"
INK = "#172033"
MUTED = "#667085"
BLUE = "#2563eb"
BLUE_DARK = "#1d4ed8"
BORDER = "#e3e8f0"
PALE_BLUE = "#eff6ff"


def safe_part(value: str, fallback: str = "") -> str:
    value = (value or "").strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip(" .-_")
    return value[:60] or fallback


# ---------------------------------------------------------------------------
# Settings (remembered between sessions)
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    try:
        with SETTINGS_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(SETTINGS_PATH)
    except OSError:
        pass  # Settings are a convenience; never block a capture over them.


# ---------------------------------------------------------------------------
# Taskbar detection and stamping
# ---------------------------------------------------------------------------

def _overlap(a: dict, b: dict) -> int:
    w = min(a["left"] + a["width"], b["left"] + b["width"]) - max(a["left"], b["left"])
    h = min(a["top"] + a["height"], b["top"] + b["height"]) - max(a["top"], b["top"])
    return max(0, w) * max(0, h)


def _clip(a: dict, b: dict) -> dict | None:
    left, top = max(a["left"], b["left"]), max(a["top"], b["top"])
    right = min(a["left"] + a["width"], b["left"] + b["width"])
    bottom = min(a["top"] + a["height"], b["top"] + b["height"])
    if right <= left or bottom <= top:
        return None
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def _contains(outer: dict, inner: dict) -> bool:
    return (outer["left"] <= inner["left"] and outer["top"] <= inner["top"]
            and inner["left"] + inner["width"] <= outer["left"] + outer["width"]
            and inner["top"] + inner["height"] <= outer["top"] + outer["height"])


def find_taskbars(monitors: list[dict]) -> list[dict]:
    """Return visible Windows taskbars in physical (MSS) pixel coordinates.

    Each entry: {"left", "top", "width", "height", "primary", "monitor"}.
    Auto-hidden taskbars (only a sliver on screen) are skipped.
    """
    if sys.platform != "win32" or not monitors:
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    # Ask for physical pixels so the rectangles line up with MSS captures,
    # whatever DPI mode the process happens to be in.
    old_ctx = None
    try:
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        old_ctx = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        old_ctx = None

    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, name, 64)
        if name.value in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd") and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                found.append(({"left": r.left, "top": r.top,
                               "width": r.right - r.left, "height": r.bottom - r.top},
                              name.value == "Shell_TrayWnd"))
        return True

    try:
        cb = proc_type(callback)
        user32.EnumWindows(cb, 0)
    finally:
        if old_ctx:
            try:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old_ctx))
            except OSError:
                pass

    taskbars = []
    for rect, primary in found:
        best = max(range(len(monitors)), key=lambda i: _overlap(rect, monitors[i]))
        clipped = _clip(rect, monitors[best])
        # A hidden/auto-hide taskbar leaves only a 1–2 px strip on screen.
        if not clipped or min(clipped["width"], clipped["height"]) < 16:
            continue
        clipped.update(primary=primary, monitor=best)
        taskbars.append(clipped)
    return taskbars


def pick_taskbar(capture_rect: dict, monitors: list[dict], taskbars: list[dict]) -> dict | None:
    """Taskbar on the monitor the capture is mostly on; else the primary; else any."""
    if not taskbars:
        return None
    if monitors:
        home = max(range(len(monitors)), key=lambda i: _overlap(capture_rect, monitors[i]))
        for tb in taskbars:
            if tb["monitor"] == home:
                return tb
    return next((tb for tb in taskbars if tb["primary"]), taskbars[0])


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def attach_taskbar(img: Image.Image, capture_rect: dict, frame: Image.Image, frame_rect: dict,
                   monitors: list[dict], taskbars: list[dict], when: datetime) -> tuple[Image.Image, str]:
    """Return (image, note). Adds the taskbar (with its clock) if it isn't already in the shot.

    `frame` is a capture of `frame_rect` taken at the same instant as `img`, so the
    attached taskbar clock matches the moment of capture.
    """
    if any(_contains(capture_rect, tb) for tb in taskbars):
        return img, "taskbar in shot"

    tb = pick_taskbar(capture_rect, monitors, taskbars)
    gap = 3
    if tb is not None:
        box = (tb["left"] - frame_rect["left"], tb["top"] - frame_rect["top"],
               tb["left"] - frame_rect["left"] + tb["width"],
               tb["top"] - frame_rect["top"] + tb["height"])
        strip = frame.crop(box)
        if tb["width"] >= tb["height"]:      # bottom/top taskbar → add underneath
            out = Image.new("RGB", (max(img.width, strip.width), img.height + gap + strip.height), "#ffffff")
            out.paste((96, 104, 120), (0, img.height, out.width, img.height + gap))
            out.paste(img, (0, 0))
            out.paste(strip, (0, img.height + gap))
        else:                                # left/right taskbar → add beside
            out = Image.new("RGB", (img.width + gap + strip.width, max(img.height, strip.height)), "#ffffff")
            out.paste((96, 104, 120), (img.width, 0, img.width + gap, out.height))
            out.paste(img, (0, 0))
            out.paste(strip, (img.width + gap, 0))
        return out, "taskbar added"

    # No visible taskbar (auto-hide, or not on Windows): stamp the time instead.
    font = _font(15)
    text = (f"Captured {when.strftime('%Y-%m-%d %I:%M:%S %p')} {when.strftime('%Z') or ''}".rstrip()
            + "  ·  taskbar was hidden, time stamped by SnapShotter")
    bar_h = 30
    try:
        text_w = int(ImageDraw.Draw(img).textlength(text, font=font)) + 20
    except Exception:
        text_w = img.width
    out = Image.new("RGB", (max(img.width, text_w), img.height + bar_h), "#ffffff")
    out.paste((31, 41, 55), (0, img.height, out.width, out.height))
    out.paste(img, (0, 0))
    ImageDraw.Draw(out).text((10, img.height + 7), text, fill="#ffffff", font=font)
    return out, "time stamp added (taskbar hidden)"


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def copy_image_to_clipboard(img: Image.Image) -> bool:
    """Put the image on the Windows clipboard (CF_DIB) so it pastes into Excel/Word/email."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    data = buf.getvalue()[14:]  # strip BITMAPFILEHEADER → DIB

    # Private DLL handles so our argtypes don't clash with other libraries.
    user32 = ctypes.WinDLL("user32")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    for _ in range(10):  # another app may briefly hold the clipboard
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(8, handle):  # CF_DIB; on success Windows owns the memory
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------------------
# Shortcut that works from any app (Windows global hotkey)
# ---------------------------------------------------------------------------

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
VK_F9, VK_F10 = 0x78, 0x79
HOTKEYS = {
    "Ctrl + Shift + F9": (MOD_CONTROL | MOD_SHIFT, VK_F9),
    "Ctrl + Alt + F9": (MOD_CONTROL | MOD_ALT, VK_F9),
    "Ctrl + Shift + F10": (MOD_CONTROL | MOD_SHIFT, VK_F10),
    "Ctrl + Alt + S": (MOD_CONTROL | MOD_ALT, ord("S")),
    "Off": None,
}
DEFAULT_HOTKEY = "Ctrl + Shift + F9"


class GlobalHotkey:
    """Registers one system-wide hotkey on a background thread.

    The thread only drops a token in a queue; the Tk main loop polls the queue,
    so all UI work stays on the main thread.
    """

    def __init__(self):
        self.events: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    def start(self, mods: int, vk: int) -> bool:
        self.stop()
        if sys.platform != "win32":
            return False
        ready = threading.Event()
        result = {"ok": False}

        def run():
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32")
            kernel32 = ctypes.WinDLL("kernel32")
            self._thread_id = kernel32.GetCurrentThreadId()
            ok = bool(user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk))
            result["ok"] = ok
            ready.set()
            if not ok:
                return
            msg = wintypes.MSG()
            try:
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == 0x0312:  # WM_HOTKEY
                        self.events.put("capture")
            finally:
                user32.UnregisterHotKey(None, 1)

        self._thread = threading.Thread(target=run, name="SnapShotterHotkey", daemon=True)
        self._thread.start()
        ready.wait(2)
        if not result["ok"]:
            self._thread = None
        return result["ok"]

    def stop(self):
        if self._thread and self._thread.is_alive() and sys.platform == "win32":
            import ctypes
            ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(1)
        self._thread = None


# ---------------------------------------------------------------------------
# Markup: yellow highlights and outlined boxes
# ---------------------------------------------------------------------------

BOX_COLORS = {"Red": (220, 38, 38), "Blue": (37, 99, 235), "Green": (22, 163, 74), "Black": (17, 24, 39)}
HIGHLIGHT_RGBA = (255, 221, 0, 100)


def render_markup(base: Image.Image, shapes: list[dict]) -> Image.Image:
    """Draw shapes (image-pixel coordinates) onto a copy of `base`."""
    out = base.convert("RGBA")
    highlights = [s for s in shapes if s["kind"] == "highlight"]
    if highlights:
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for s in highlights:
            d.rectangle(s["box"], fill=HIGHLIGHT_RGBA)
        out = Image.alpha_composite(out, layer)
    d = ImageDraw.Draw(out)
    width = max(3, round(max(base.size) / 600))
    for s in shapes:
        if s["kind"] == "box":
            d.rectangle(s["box"], outline=BOX_COLORS.get(s.get("color"), BOX_COLORS["Red"]) + (255,), width=width)
    for s in shapes:  # redactions last, so nothing can show through them
        if s["kind"] == "redact":
            d.rectangle(s["box"], fill=(0, 0, 0, 255))
    return out.convert("RGB")


class MarkupEditor:
    """Window for adding highlights and boxes to a saved capture.

    The original file is never changed; on save a "<name>_marked.png" copy is written
    and `on_done(path)` is called. Skipping/closing calls `on_done(None)`.
    """

    def __init__(self, master: tk.Misc, image_path: Path, on_done):
        self.path = Path(image_path)
        self.on_done = on_done
        self.base = Image.open(self.path).convert("RGB")
        self.shapes: list[dict] = []
        self.tool = tk.StringVar(value="highlight")
        self.color = tk.StringVar(value="Red")
        self._drag = None
        self._finished = False

        win = self.win = tk.Toplevel(master)
        win.title(f"Mark up — {self.path.name}")
        win.configure(bg=BG)
        win.minsize(900, 0)  # room for the toolbar even when the screenshot is small
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        self.scale = min(1.0, (sw * 0.88) / self.base.width, (sh * 0.72) / self.base.height)
        self.view_size = (max(1, round(self.base.width * self.scale)), max(1, round(self.base.height * self.scale)))

        bar = tk.Frame(win, bg=BG, padx=12, pady=10)
        bar.pack(fill="x")
        for value, text in (("highlight", "🖍  Highlight"), ("box", "▭  Box"), ("redact", "■  Redact")):
            tk.Radiobutton(bar, text=text, value=value, variable=self.tool, indicatoron=False,
                           font=("Segoe UI", 10), padx=12, pady=5, bg="#ffffff", selectcolor="#dbeafe",
                           relief="ridge", cursor="hand2").pack(side="left", padx=(0, 6))
        # Colour dots for the Box tool: click one to pick it.
        self._dots = tk.Canvas(bar, width=len(BOX_COLORS) * 26 + 4, height=28, bg=BG, highlightthickness=0,
                               cursor="hand2")
        self._dots.pack(side="left", padx=(8, 0))
        self._dots.bind("<Button-1>", self._pick_color)
        self._draw_dots()
        ttk.Button(bar, text="↶ Undo", command=self.undo).pack(side="left", padx=(14, 0))
        ttk.Button(bar, text="Clear", command=self.clear).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Done", style="Primary.TButton", command=self.save).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self.skip).pack(side="right", padx=(0, 8))

        tk.Label(win, text="Drag on the image.   Ctrl+Z undo · Enter done · Esc cancel.   Your original screenshot "
                           "is kept unchanged (so Redact hides things only in the marked copy).",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=12)
        self.canvas = tk.Canvas(win, width=self.view_size[0], height=self.view_size[1],
                                highlightthickness=1, highlightbackground=BORDER, cursor="crosshair")
        self.canvas.pack(padx=12, pady=(6, 12))
        self._redraw()

        self.canvas.bind("<ButtonPress-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        win.bind("<Control-z>", lambda _e: self.undo())
        win.bind("<Return>", lambda _e: self.save())
        win.bind("<Escape>", lambda _e: self.skip())
        win.protocol("WM_DELETE_WINDOW", self.skip)

        # Come to the front even if SnapShotter's main window is hidden/minimized.
        win.lift()
        win.attributes("-topmost", True)
        win.after(400, lambda: win.winfo_exists() and win.attributes("-topmost", False))
        win.focus_force()

    def _draw_dots(self):
        c = self._dots
        c.delete("all")
        for i, (name, rgb) in enumerate(BOX_COLORS.items()):
            x = 4 + i * 26
            if name == self.color.get():
                c.create_oval(x - 1, 2, x + 23, 26, outline=INK, width=2)
            c.create_oval(x + 3, 6, x + 19, 22, fill="#%02x%02x%02x" % rgb, outline="")

    def _pick_color(self, event):
        index = max(0, min(len(BOX_COLORS) - 1, (event.x - 4) // 26))
        self.color.set(list(BOX_COLORS)[index])
        self.tool.set("box")
        self._draw_dots()

    def _redraw(self):
        view = render_markup(self.base, self.shapes)
        if self.scale < 1:
            view = view.resize(self.view_size, Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(view)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _down(self, e):
        self._drag = (e.x, e.y, self.canvas.create_rectangle(e.x, e.y, e.x, e.y, dash=(4, 2), width=2,
                                                             outline={"highlight": "#f59e0b", "redact": "#111827"}.get(
                                                                 self.tool.get(),
                                                                 "#%02x%02x%02x" % BOX_COLORS[self.color.get()])))

    def _move(self, e):
        if self._drag:
            self.canvas.coords(self._drag[2], self._drag[0], self._drag[1], e.x, e.y)

    def _up(self, e):
        if not self._drag:
            return
        x0, y0, _item = self._drag
        self._drag = None
        x1, x2 = sorted((x0, e.x))
        y1, y2 = sorted((y0, e.y))
        if x2 - x1 >= 3 and y2 - y1 >= 3:
            s = self.scale
            box = [max(0, round(x1 / s)), max(0, round(y1 / s)),
                   min(self.base.width - 1, round(x2 / s)), min(self.base.height - 1, round(y2 / s))]
            self.shapes.append({"kind": self.tool.get(), "box": box, "color": self.color.get()})
        self._redraw()

    def undo(self):
        if self.shapes:
            self.shapes.pop()
            self._redraw()

    def clear(self):
        self.shapes.clear()
        self._redraw()

    def _finish(self, result):
        if self._finished:
            return
        self._finished = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.on_done(result)

    def skip(self):
        self._finish(None)

    def save(self):
        if not self.shapes:
            self.skip()
            return
        out = self.path.with_name(f"{self.path.stem}_marked.png")
        n = 2
        while out.exists():
            out = self.path.with_name(f"{self.path.stem}_marked_{n}.png")
            n += 1
        try:
            render_markup(self.base, self.shapes).save(out)
        except Exception as exc:
            messagebox.showerror("Couldn't save", str(exc), parent=self.win)
            return
        self._finish(out)


class Tooltip:
    """Plain hover tip for a widget."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip, self._job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._job = self.widget.after(450, self._show)

    def _show(self):
        if self.tip or not self.widget.winfo_ismapped():
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        tk.Label(self.tip, text=self.text, bg="#111827", fg="white", font=("Segoe UI", 9),
                 justify="left", padx=9, pady=5).pack()
        self.tip.geometry(f"+{x}+{y}")

    def _hide(self, _e=None):
        if self._job:
            self.widget.after_cancel(self._job)
            self._job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


class SnapShotterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SnapShotter")
        self.root.geometry("800x920")
        self.root.minsize(740, 820)
        self.root.configure(bg=BG)

        self.settings = load_settings()
        saved_folders = [f for f in self.settings.get("custom_folders", []) if isinstance(f, str) and f.strip()]
        self.custom_folders: list[str] = saved_folders or [str(DEFAULT_FOLDER)]
        self.save_folder = tk.StringVar(value=self.settings.get("save_folder") or self.custom_folders[0])
        self.prefix = tk.StringVar(value=self.settings.get("filename_prefix", ""))
        self.include_taskbar = tk.BooleanVar(value=self.settings.get("include_taskbar", True))
        self.entity = tk.StringVar()
        self.account = tk.StringVar()
        self.period = tk.StringVar(value=datetime.now().strftime("%Y-%m"))
        self.reference = tk.StringVar()
        self.mode = tk.StringVar(value="region")
        self.monitor_choice = tk.StringVar()
        self.delay = tk.StringVar(value="No delay")
        self.open_after = tk.BooleanVar(value=self.settings.get("open_after", False))
        self.copy_clipboard = tk.BooleanVar(value=self.settings.get("copy_clipboard", True))
        self.markup_after = tk.BooleanVar(value=self.settings.get("markup_after", False))
        hk = self.settings.get("hotkey", DEFAULT_HOTKEY)
        self.hotkey_name = tk.StringVar(value=hk if hk in HOTKEYS else DEFAULT_HOTKEY)
        self.hotkey_status = tk.StringVar(value="")
        self.hotkey = GlobalHotkey()
        self._busy = False            # a capture / markup is in progress
        self._from_hotkey = False     # current capture was started from another app
        self._was_minimized = False
        self._toast = None
        self._index_waiting = False
        self._label_boxes = {}
        self.status = tk.StringVar(value="Ready.")
        self.monitors: list[dict] = []
        self.selected_monitor_index = 0
        self.primary_monitor_index = 0
        self.monitor_hitboxes = []
        self.history_paths: list[Path] = []
        self._build_ui()
        self.refresh_monitors()
        self.refresh_history()
        self._update_name_preview()
        self._fit_window()
        self._ui_ready = True
        self.root.bind("<F9>", lambda _e: self.capture())
        self.root.bind("<Escape>", lambda _e: None)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_hotkey()
        self.root.after(100, self._poll_hotkey)
        self._write_index_row()  # write any index rows that were waiting from last time

    # ----- shortcut from any app -------------------------------------------
    def _apply_hotkey(self):
        name = self.hotkey_name.get()
        combo = HOTKEYS.get(name)
        self.hotkey.stop()
        if combo is None:
            self.hotkey_status.set("Off. Use F9 inside SnapShotter.")
        elif sys.platform != "win32":
            self.hotkey_status.set("Available on Windows only.")
        elif self.hotkey.start(*combo):
            self.hotkey_status.set(f"✓ Active. Press {name} from Excel, your ERP, a browser…")
        else:
            self.hotkey_status.set(f"⚠ {name} is already used by another program. Pick a different shortcut.")
        ok = combo is not None and self.hotkey_status.get().startswith("✓")
        self.shortcut_hint.configure(
            text=(f"⌨ {name} works in any app" if ok else
                  "⌨ F9 in this window" if combo is None else
                  f"⚠ {name} unavailable — see Settings"),
            fg="#15803d" if ok else ("#b45309" if combo is not None else MUTED))
        if not self._busy:
            self.status.set(f"Ready. Click Capture, or press {name} in any app." if ok
                            else "Ready. Click Capture or press F9.")
        self._persist()

    def _poll_hotkey(self):
        try:
            while True:
                self.hotkey.events.get_nowait()
                if not self._busy:
                    self.capture(from_hotkey=True)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_hotkey)

    def _fit_window(self, keep_position: bool = False):
        """Size the window to its content, but never taller than the screen's usable area."""
        self.root.update_idletasks()
        need_w = max(800, self._outer.winfo_reqwidth() + 20)
        need_h = self._outer.winfo_reqheight() + 4
        max_h = self.root.winfo_screenheight() - 90  # leave room for the taskbar/title bar
        self.root.minsize(740, min(need_h, max_h, 480))
        if keep_position:
            self.root.geometry(f"{max(need_w, self.root.winfo_width())}x{min(need_h, max_h)}")
        else:
            self.root.geometry(f"{need_w}x{min(need_h, max_h)}+40+20")

    def _persist(self):
        self.settings.pop("organize", None)
        self.settings.update(
            save_folder=self.save_folder.get().strip(),
            custom_folders=self.custom_folders,
            filename_prefix=self.prefix.get().strip(),
            include_taskbar=bool(self.include_taskbar.get()),
            open_after=bool(self.open_after.get()),
            copy_clipboard=bool(self.copy_clipboard.get()),
            markup_after=bool(self.markup_after.get()),
            hotkey=self.hotkey_name.get(),
        )
        save_settings(self.settings)

    def _on_close(self):
        self._persist()
        self.hotkey.stop()
        self.root.destroy()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=CARD, foreground=INK, font=("Segoe UI", 11, "bold"))
        style.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 7))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 12),
                        background=BLUE, foreground="white")
        style.map("Primary.TButton", background=[("active", BLUE_DARK), ("pressed", BLUE_DARK)],
                  foreground=[("!disabled", "white")])
        style.configure("TCombobox", padding=6, font=("Segoe UI", 9))
        style.configure("TEntry", padding=6, font=("Segoe UI", 9))
        style.configure("TCheckbutton", background=CARD, foreground=INK, font=("Segoe UI", 9))

        # Scrollable body: if the window is shorter than its content (small or
        # scaled screens), a scrollbar appears so every setting stays reachable.
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)
        canvas = self._body_canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        vsb = self._body_scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        outer = self._outer = ttk.Frame(canvas, padding=(22, 18))
        body_item = canvas.create_window(0, 0, window=outer, anchor="nw")

        def relayout(_e=None):
            view_h = canvas.winfo_height()
            need_h = outer.winfo_reqheight()
            canvas.itemconfigure(body_item, width=canvas.winfo_width(), height=max(view_h, need_h))
            canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), max(view_h, need_h)))
            if need_h > view_h + 1:
                if not vsb.winfo_ismapped():
                    vsb.pack(side="right", fill="y", before=canvas)
            elif vsb.winfo_ismapped():
                vsb.pack_forget()
                canvas.yview_moveto(0)

        canvas.bind("<Configure>", relayout)
        outer.bind("<Configure>", lambda _e: canvas.after_idle(relayout))

        def wheel(event):
            w = event.widget
            # Let lists and drop-downs scroll themselves; ignore other windows (markup, overlay).
            if isinstance(w, (str, tk.Listbox)) or not vsb.winfo_ismapped():
                return
            try:
                if w.winfo_toplevel() is not self.root:
                    return
            except (tk.TclError, AttributeError):
                return
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        self.root.bind_all("<MouseWheel>", wheel, add="+")

        # ---------------------------------------------------------------- header
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        right = ttk.Frame(header)
        right.pack(side="right", anchor="n")
        settings_btn = ttk.Button(right, text="⚙  Settings", command=self.open_settings)
        settings_btn.pack(side="right")
        Tooltip(settings_btn, "Shortcut key, clipboard, taskbar clock, filename prefix")
        self.shortcut_hint = tk.Label(right, text="", bg=BG, fg="#15803d", font=("Segoe UI", 9, "bold"))
        self.shortcut_hint.pack(side="right", padx=(0, 12), pady=(6, 0))
        ttk.Label(header, text="SnapShotter", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(header, text="Capture it. It's labeled, dated, filed and ready to paste.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        # -------------------------------------------------------------- labels
        context = self._card(outer, "Label",
                             "Optional. Whatever you fill in goes into the file name and the evidence index.")
        grid = ttk.Frame(context, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        fields = (("entity", "Entity / company", 0, 0), ("period", "Period", 0, 2),
                  ("account", "Account", 1, 0), ("reference", "JE / ticket / ref.", 1, 2))
        for key, text, r, c in fields:
            ttk.Label(grid, text=text, style="Hint.TLabel").grid(row=r, column=c, sticky="w", padx=(0, 8), pady=4)
            box = ttk.Combobox(grid, textvariable=getattr(self, key), values=self._label_values(key))
            box.grid(row=r, column=c + 1, sticky="ew", padx=(0, 14) if c == 0 else 0, pady=4)
            self._no_wheel(box)
            Tooltip(box, "Type, or pick one you've used before from the drop-down")
            self._label_boxes[key] = box
        preview_line = ttk.Frame(context, style="Card.TFrame")
        preview_line.pack(fill="x", pady=(8, 0))
        clear_btn = ttk.Button(preview_line, text="Clear", command=self.clear_labels)
        clear_btn.pack(side="right")
        Tooltip(clear_btn, "Empty entity, account and reference; reset period to this month")
        ttk.Label(preview_line, text="Will be saved as", style="Hint.TLabel").pack(side="left")
        self.name_preview = tk.Label(preview_line, text="", bg=CARD, fg=BLUE_DARK, font=("Consolas", 9), anchor="w")
        self.name_preview.pack(side="left", padx=(6, 0), fill="x", expand=True)

        # ------------------------------------------------------------- capture
        capture = self._card(outer, "Capture", None)
        tiles = ttk.Frame(capture, style="Card.TFrame")
        tiles.pack(fill="x")
        self._tiles = {}
        for i, (value, icon, title, subtitle) in enumerate(MODE_TILES):
            tile = self._tile(tiles, value, icon, title, subtitle)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 4, 0 if i == 3 else 4))
            tiles.columnconfigure(i, weight=1, uniform="tiles")

        # Display picker: only shown for "One screen".
        self.picker = ttk.Frame(capture, style="Card.TFrame")
        picker_head = ttk.Frame(self.picker, style="Card.TFrame")
        picker_head.pack(fill="x", pady=(10, 5))
        ttk.Label(picker_head, text="Click the display to capture:", style="Hint.TLabel").pack(side="left")
        ttk.Button(picker_head, text="↻ Refresh displays", command=self.refresh_monitors).pack(side="right")
        self.monitor_canvas = tk.Canvas(self.picker, height=110, bg="#f8fafc",
                                        highlightthickness=1, highlightbackground=BORDER, cursor="hand2")
        self.monitor_canvas.pack(fill="x")
        self.monitor_canvas.bind("<Button-1>", self._monitor_canvas_click)
        self.monitor_canvas.bind("<Configure>", lambda _e: self._draw_monitor_picker())
        self.display_summary = ttk.Label(self.picker, text="", style="Hint.TLabel")
        self.display_summary.pack(anchor="w", pady=(5, 0))

        self.capture_btn = ttk.Button(capture, text="Capture", style="Primary.TButton", command=self.capture)
        self.capture_btn.pack(fill="x", pady=(12, 0))
        self.capture_opts = ttk.Frame(capture, style="Card.TFrame")
        self.capture_opts.pack(fill="x", pady=(8, 0))
        ttk.Label(self.capture_opts, textvariable=self.status, style="Hint.TLabel").pack(side="left")
        delay_box = ttk.Combobox(self.capture_opts, textvariable=self.delay, state="readonly", width=11,
                                 values=["No delay", "3 seconds", "5 seconds", "10 seconds"])
        delay_box.pack(side="right")
        self._no_wheel(delay_box)
        Tooltip(delay_box, "Gives you time to open a menu or drop-down before the capture")
        cb = ttk.Checkbutton(self.capture_opts, text="Mark up after capture",
                             variable=self.markup_after, command=self._persist)
        cb.pack(side="right", padx=(0, 14))
        Tooltip(cb, "Always open the markup window (highlight, box, redact) after a capture.\n"
                    "You can also click Mark up on the preview that appears after any capture.")

        # ------------------------------------------------------------- save to
        filing = self._card(outer, "Save to", None)
        folder_line = ttk.Frame(filing, style="Card.TFrame")
        folder_line.pack(fill="x")
        self.folder_box = ttk.Combobox(folder_line, textvariable=self.save_folder, values=self.custom_folders)
        self.folder_box.pack(side="left", fill="x", expand=True)
        self.folder_box.bind("<<ComboboxSelected>>", lambda _e: self._folder_changed())
        self.folder_box.bind("<FocusOut>", lambda _e: self._folder_changed())
        self.folder_box.bind("<Return>", lambda _e: self._folder_changed())
        self._no_wheel(self.folder_box)
        Tooltip(self.folder_box, "Folders you've used are remembered here")
        for text, cmd, tip in (("Browse…", self.choose_folder, "Choose a different folder"),
                               ("Open", self.open_folder, "Open this folder in File Explorer")):
            b = ttk.Button(folder_line, text=text, command=cmd)
            b.pack(side="left", padx=(6, 0))
            Tooltip(b, tip)
        forget = tk.Label(filing, text="Remove this folder from the list", bg=CARD, fg=MUTED,
                          font=("Segoe UI", 8, "underline"), cursor="hand2")
        forget.pack(anchor="e", pady=(4, 0))
        forget.bind("<Button-1>", lambda _e: self.remove_custom_folder())
        Tooltip(forget, "Only takes it off the drop-down. Nothing is deleted.")

        # ---------------------------------------------------- recent evidence
        recent = self._card(outer, "Recent", None, expand=True)
        row = ttk.Frame(recent, style="Card.TFrame")
        row.pack(fill="both", expand=True, pady=(2, 0))
        holder = tk.Frame(row, width=218, height=116, bg="#f8fafc",
                          highlightthickness=1, highlightbackground=BORDER)
        holder.pack(side="right", padx=(8, 0))
        holder.pack_propagate(False)
        self.preview = tk.Label(holder, bg="#f8fafc", fg=MUTED, font=("Segoe UI", 9), cursor="hand2")
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Button-1>", self.open_selected)
        self.history = tk.Listbox(row, height=5, activestyle="none", relief="flat", bd=0,
                                  bg="#f8fafc", fg=INK, font=("Segoe UI", 9),
                                  selectbackground="#dbeafe", selectforeground=INK,
                                  highlightthickness=1, highlightbackground=BORDER, exportselection=False)
        self.history.pack(side="left", fill="both", expand=True)
        self.history.bind("<Double-Button-1>", self.open_selected)
        self.history.bind("<<ListboxSelect>>", lambda _e: self._update_history_buttons())
        buttons = ttk.Frame(recent, style="Card.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        self._history_buttons = []
        for text, cmd, tip in (("Open", self.open_selected, "Open the image (or double-click it)"),
                               ("🖍 Mark up", self.markup_selected,
                                "Highlight, box or redact. Saves a separate …_marked copy"),
                               ("📋 Copy", self.copy_selected, "Copy the image to paste with Ctrl+V"),
                               ("Show in folder", self.show_selected, "Open File Explorer with this file selected")):
            b = ttk.Button(buttons, text=text, command=cmd)
            b.pack(side="left", padx=(0, 6))
            Tooltip(b, tip)
            self._history_buttons.append(b)
        ttk.Button(buttons, text="↻", width=3, command=self.refresh_history).pack(side="right")

        for var in (self.entity, self.account, self.period, self.reference, self.prefix, self.mode):
            var.trace_add("write", lambda *_a: self._update_name_preview())
        self._select_tile(self.mode.get())

    # ----- small UI helpers ---------------------------------------------------
    def _no_wheel(self, widget):
        """Stop the mouse wheel from silently changing a drop-down's value; scroll the page instead."""
        def on_wheel(event):
            if self._body_scrollbar.winfo_ismapped():
                self._body_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"
        widget.bind("<MouseWheel>", on_wheel)

    def _card(self, parent, title, subtitle, expand=False):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 13))
        card.pack(fill="both" if expand else "x", expand=expand, pady=(0, 10))
        ttk.Label(card, text=title, style="Card.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(card, text=subtitle, style="Hint.TLabel").pack(anchor="w", pady=(2, 9))
        else:
            ttk.Frame(card, style="Card.TFrame", height=6).pack()
        return card

    def _tile(self, parent, value, icon, title, subtitle):
        frame = tk.Frame(parent, bg="#f8fafc", highlightthickness=2, highlightbackground=BORDER,
                         padx=8, pady=8, cursor="hand2")
        parts = [tk.Label(frame, text=icon, bg="#f8fafc", fg=INK, font=("Segoe UI Symbol", 16)),
                 tk.Label(frame, text=title, bg="#f8fafc", fg=INK, font=("Segoe UI", 10, "bold")),
                 tk.Label(frame, text=subtitle, bg="#f8fafc", fg=MUTED, font=("Segoe UI", 8),
                          wraplength=150, justify="center")]
        for p in parts:
            p.pack()
        for w in [frame] + parts:
            w.bind("<Button-1>", lambda _e, v=value: self._select_tile(v))
        self._tiles[value] = (frame, parts)
        return frame

    def _select_tile(self, value):
        self.mode.set(value)
        for v, (frame, parts) in self._tiles.items():
            on = v == value
            bg = "#e8f0fe" if on else "#f8fafc"
            frame.configure(bg=bg, highlightbackground=BLUE if on else BORDER)
            for p in parts:
                p.configure(bg=bg)
            parts[1].configure(fg=BLUE_DARK if on else INK)
        if value == "monitor":
            if not self.picker.winfo_ismapped():
                self.picker.pack(fill="x", before=self.capture_btn)
            self._draw_monitor_picker()
        elif self.picker.winfo_ismapped():
            self.picker.pack_forget()
        self._mode_changed()
        if getattr(self, "_ui_ready", False):
            self._fit_window(keep_position=True)

    def _preview_label(self) -> str:
        mode = self.mode.get()
        if mode == "region":
            return "Region"
        if mode == "screen":
            return "All-Screens"
        if mode == "monitor":
            return f"Display-{self.selected_monitor_index + 1}"
        return "Display-1 (one file per display)"

    def _update_name_preview(self):
        if not hasattr(self, "name_preview"):
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        label = self._preview_label()
        extra = ""
        if label.endswith("(one file per display)"):
            label, extra = "Display-1", "   (one file per display)"
        self.name_preview.configure(text=self._file_stem(stamp, label) + ".png" + extra)

    def clear_labels(self):
        for var in (self.entity, self.account, self.reference):
            var.set("")
        self.period.set(datetime.now().strftime("%Y-%m"))

    def _update_history_buttons(self):
        state = "!disabled" if self._selected_path() else "disabled"
        for b in self._history_buttons:
            b.state([state])
        self._update_preview()

    # ----- settings window -----------------------------------------------------
    def open_settings(self):
        if getattr(self, "_settings_win", None) is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        win = self._settings_win = tk.Toplevel(self.root)
        win.title("SnapShotter settings")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        body = ttk.Frame(win, padding=18)
        body.pack(fill="both", expand=True)

        sec = self._card(body, "Shortcut from any app",
                         "Capture while you're in Excel, your ERP or a browser. SnapShotter can stay minimized.")
        line = ttk.Frame(sec, style="Card.TFrame")
        line.pack(fill="x")
        hk_box = ttk.Combobox(line, textvariable=self.hotkey_name, values=list(HOTKEYS), state="readonly", width=20)
        hk_box.pack(side="left")
        hk_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_hotkey())
        ttk.Label(sec, textvariable=self.hotkey_status, style="Hint.TLabel", wraplength=470).pack(anchor="w", pady=(6, 0))

        sec = self._card(body, "File names", "Optional word at the start of every file name, e.g. Screenshot or Q4-Close.")
        line = ttk.Frame(sec, style="Card.TFrame")
        line.pack(fill="x")
        ttk.Label(line, text="Prefix:", style="Hint.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(line, textvariable=self.prefix, width=24).pack(side="left")

        sec = self._card(body, "Every capture", None)
        ttk.Checkbutton(sec, text="Copy to the clipboard, ready to paste with Ctrl+V",
                        variable=self.copy_clipboard, command=self._persist).pack(anchor="w")
        ttk.Checkbutton(sec, text="Include the taskbar so the date/time clock shows in the image",
                        variable=self.include_taskbar, command=self._persist).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(sec, text="Open the image after capture",
                        variable=self.open_after, command=self._persist).pack(anchor="w", pady=(6, 0))

        ttk.Button(body, text="Done", style="Primary.TButton",
                   command=lambda: (self._persist(), win.destroy())).pack(anchor="e")
        win.protocol("WM_DELETE_WINDOW", lambda: (self._persist(), win.destroy()))
        win.update_idletasks()
        x = self.root.winfo_rootx() + 60
        y = self.root.winfo_rooty() + 60
        win.geometry(f"+{x}+{y}")
        win.focus_force()

    def _mode_changed(self):
        self._draw_monitor_picker()
        self._update_name_preview()

    def _monitor_canvas_click(self, event):
        for index, (x1, y1, x2, y2) in enumerate(self.monitor_hitboxes):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.selected_monitor_index = index
                self._draw_monitor_picker()
                self._update_name_preview()
                break

    def _draw_monitor_picker(self):
        if not hasattr(self, "monitor_canvas"):
            return
        if not self.picker.winfo_ismapped():
            return
        canvas = self.monitor_canvas
        canvas.delete("all")
        self.monitor_hitboxes = []
        if not self.monitors:
            canvas.create_text(18, 24, anchor="nw", text="No displays detected.",
                               fill=MUTED, font=("Segoe UI", 10))
            return

        # Preserve the relative arrangement reported by Windows/MSS while fitting
        # all displays into the available picker area.
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 110)
        min_left = min(m["left"] for m in self.monitors)
        min_top = min(m["top"] for m in self.monitors)
        max_right = max(m["left"] + m["width"] for m in self.monitors)
        max_bottom = max(m["top"] + m["height"] for m in self.monitors)
        virtual_w = max(1, max_right - min_left)
        virtual_h = max(1, max_bottom - min_top)
        pad_x, pad_y = 28, 23
        available_w, available_h = max(100, width - 2 * pad_x), max(60, height - 2 * pad_y)
        scale = min(available_w / virtual_w, available_h / virtual_h)
        total_w, total_h = virtual_w * scale, virtual_h * scale
        offset_x = (width - total_w) / 2
        offset_y = (height - total_h) / 2

        for index, mon in enumerate(self.monitors):
            x1 = offset_x + (mon["left"] - min_left) * scale
            y1 = offset_y + (mon["top"] - min_top) * scale
            x2 = x1 + mon["width"] * scale
            y2 = y1 + mon["height"] * scale
            # Ensure tiny/portrait displays still have a usable click target.
            if x2 - x1 < 52:
                x2 = x1 + 52
            if y2 - y1 < 38:
                y2 = y1 + 38
            selected = index == self.selected_monitor_index
            fill = "#dbeafe" if selected else "#ffffff"
            outline = BLUE if selected else "#aeb8c8"
            canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline,
                                    width=3 if selected else 1)
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            canvas.create_text(cx, cy - 8, text=f"Display {index + 1}" +
                               ("  ✓" if selected else ""),
                               fill=BLUE_DARK if selected else INK,
                               font=("Segoe UI", 10, "bold"))
            canvas.create_text(cx, cy + 11,
                               text=f"{mon['width']} × {mon['height']}",
                               fill=MUTED, font=("Segoe UI", 8))
            self.monitor_hitboxes.append((x1, y1, x2, y2))

        chosen = self.monitors[self.selected_monitor_index]
        primary_text = " · Primary display" if self.selected_monitor_index == self.primary_monitor_index else ""
        self.display_summary.configure(
            text=f"Selected: Display {self.selected_monitor_index + 1} "
                 f"({chosen['width']} × {chosen['height']}){primary_text}.")

    def refresh_monitors(self):
        try:
            with _new_mss() as sct:
                all_monitors = [dict(m) for m in sct.monitors[1:]]
            previous = self.selected_monitor_index
            self.monitors = all_monitors
            if not self.monitors:
                self.selected_monitor_index = 0
                self.primary_monitor_index = 0
            else:
                # Windows' primary monitor normally has its top-left at (0, 0).
                # Use it as the initial default; retain an existing selection on refresh.
                self.primary_monitor_index = next(
                    (i for i, m in enumerate(self.monitors)
                     if m["left"] == 0 and m["top"] == 0), 0)
                if not getattr(self, "_has_initialized_monitor_selection", False):
                    self.selected_monitor_index = self.primary_monitor_index
                    self._has_initialized_monitor_selection = True
                else:
                    self.selected_monitor_index = min(previous, len(self.monitors) - 1)
            self._draw_monitor_picker()
        except Exception as exc:
            self.display_summary.configure(text=f"Could not detect displays: {exc}")

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.save_folder.get() or str(Path.home()))
        if folder:
            self.save_folder.set(str(Path(folder)))
            self._remember_folder(self.save_folder.get())
            self._folder_changed()

    def _folder_changed(self):
        self.refresh_history()
        self._persist()

    def _remember_folder(self, folder: str):
        """Folders you use are added to the drop-down automatically."""
        folder = folder.strip()
        if folder and not any(self._same_folder(folder, f) for f in self.custom_folders):
            self.custom_folders.append(folder)
            del self.custom_folders[:-15]
            self.folder_box.configure(values=self.custom_folders)

    LABEL_KEYS = ("entity", "account", "period", "reference")

    def _label_values(self, key: str) -> list[str]:
        history = [v for v in self.settings.get("label_history", {}).get(key, []) if isinstance(v, str)]
        if key != "period":
            return history
        now = datetime.now()
        last = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        suggestions = [now.strftime("%Y-%m"), f"{last[0]}-{last[1]:02d}"]
        return suggestions + [v for v in history if v not in suggestions]

    def _remember_labels(self):
        """Keep what you typed so it's one click away next time."""
        history = self.settings.setdefault("label_history", {})
        for key in self.LABEL_KEYS:
            value = getattr(self, key).get().strip()
            if value:
                items = [v for v in history.get(key, []) if v != value]
                history[key] = [value] + items[:11]
            if key in getattr(self, "_label_boxes", {}):
                self._label_boxes[key].configure(values=self._label_values(key))

    @staticmethod
    def _same_folder(a: str, b: str) -> bool:
        return os.path.normcase(os.path.normpath(a.strip())) == os.path.normcase(os.path.normpath(b.strip()))

    def add_custom_folder(self):
        folder = self.save_folder.get().strip()
        if not folder:
            messagebox.showinfo("Save folder", "Type or Browse to a folder first.")
            return
        if any(self._same_folder(folder, f) for f in self.custom_folders):
            self.status.set("That folder is already in your saved list.")
            return
        self.custom_folders.append(folder)
        self.folder_box.configure(values=self.custom_folders)
        self._persist()
        self.status.set(f"Saved folder added: {folder}")

    def remove_custom_folder(self):
        folder = self.save_folder.get().strip()
        match = next((f for f in self.custom_folders if self._same_folder(folder, f)), None)
        if match is None:
            self.status.set("The current folder isn't in your saved list.")
            return
        if not messagebox.askyesno("Remove from list",
                                   f"Remove this folder from the saved list?\n\n{match}\n\n"
                                   "Nothing is deleted on disk; it just won't appear in the list."):
            return
        self.custom_folders.remove(match)
        if not self.custom_folders:
            self.custom_folders.append(str(DEFAULT_FOLDER))
        self.folder_box.configure(values=self.custom_folders)
        self.save_folder.set(self.custom_folders[0])
        self._folder_changed()
        self.status.set(f"Removed from saved list: {match}")

    def _destination(self, stamp: str, capture_label: str) -> Path:
        # Screenshots go straight into the chosen folder — no subfolders.
        root = Path(self.save_folder.get()).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        stem = self._file_stem(stamp, capture_label)
        path = root / f"{stem}.png"
        n = 2
        while path.exists():
            path = root / f"{stem}_{n}.png"
            n += 1
        return path

    def _file_stem(self, stamp: str, capture_label: str) -> str:
        pieces = [p for p in (safe_part(self.prefix.get()), stamp) if p]
        for value in (self.entity.get(), self.account.get(), self.period.get(), self.reference.get()):
            part = safe_part(value)
            if part:
                pieces.append(part)
        if capture_label:
            pieces.append(capture_label)
        return "_".join(pieces)

    @staticmethod
    def _image(sct, monitor):
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)

    def capture(self, from_hotkey: bool = False):
        if self._busy:
            return
        if not self.monitors:
            messagebox.showerror("No displays found", "Connect or enable a display, then choose Refresh displays.")
            return
        self._busy = True
        self._from_hotkey = from_hotkey
        self._was_minimized = self.root.state() in ("iconic", "withdrawn")
        self._close_toast()  # never let our own notification end up in the shot
        delay = {"No delay": 0, "3 seconds": 3, "5 seconds": 5, "10 seconds": 10}.get(self.delay.get(), 0)
        self.status.set("Get ready…" if delay else "Preparing capture…")
        self.root.withdraw()
        self.root.after(delay * 1000 + 200, self._perform_capture)

    def _restore_window(self):
        """Bring SnapShotter back — but stay out of the way after a capture from another app."""
        self._busy = False
        if self._from_hotkey:
            if self._was_minimized:
                self.root.iconify()
            else:
                self.root.deiconify()
        else:
            self.root.deiconify()
            self.root.lift()

    def _close_toast(self):
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
            self._toast = None

    def _show_toast(self, title: str, detail: str = "", image_path: Path | None = None,
                    actions=(), seconds: float = 7):
        """Quiet notice in the bottom-right corner, like a screenshot preview.

        Never needs a click: it fades on its own, but stays while the mouse is over it.
        `actions` is a list of (label, callback); clicking the thumbnail runs the first one.
        """
        self._close_toast()
        bg = "#111827"
        t = self._toast = tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(bg=bg, padx=12, pady=12)

        def run(callback):
            self._close_toast()
            callback()

        if image_path is not None:
            try:
                with Image.open(image_path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((190, 116))
                    photo = ImageTk.PhotoImage(im)
                thumb = tk.Label(t, image=photo, bg=bg, bd=0, highlightthickness=1,
                                 highlightbackground="#4b5563", cursor="hand2" if actions else "")
                thumb.image = photo
                thumb.pack(side="left", padx=(0, 12))
                if actions:
                    thumb.bind("<Button-1>", lambda _e: run(actions[0][1]))
            except Exception:
                pass
        right = tk.Frame(t, bg=bg)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text=title, bg=bg, fg="white", font=("Segoe UI", 10, "bold"),
                 anchor="w", justify="left").pack(fill="x")
        if detail:
            tk.Label(right, text=detail, bg=bg, fg="#d1d5db", font=("Segoe UI", 9),
                     anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(2, 0))
        if actions:
            row = tk.Frame(right, bg=bg)
            row.pack(anchor="w", pady=(9, 0))
            for text, callback in actions:
                tk.Button(row, text=text, command=lambda cb=callback: run(cb), bg="#374151", fg="white",
                          activebackground="#4b5563", activeforeground="white", relief="flat", bd=0,
                          padx=10, pady=4, font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=(0, 6))
        t.update_idletasks()
        x = t.winfo_screenwidth() - t.winfo_reqwidth() - 24
        y = t.winfo_screenheight() - t.winfo_reqheight() - 80
        t.geometry(f"+{x}+{y}")

        deadline = [time.monotonic() + seconds]

        def tick():
            if self._toast is not t:
                return
            try:
                px, py = t.winfo_pointerxy()
                inside = (t.winfo_rootx() <= px <= t.winfo_rootx() + t.winfo_width()
                          and t.winfo_rooty() <= py <= t.winfo_rooty() + t.winfo_height())
            except tk.TclError:
                return
            if inside:
                deadline[0] = time.monotonic() + 2.5   # stay while the mouse is on it
            elif time.monotonic() >= deadline[0]:
                self._close_toast()
                return
            t.after(300, tick)

        t.after(300, tick)

    def _grab_frame(self):
        """One capture of the whole desktop plus the taskbars visible at that instant."""
        with _new_mss() as sct:
            virtual = dict(sct.monitors[0])
            monitors = [dict(m) for m in sct.monitors[1:]]
            frame = self._image(sct, virtual)
        try:
            taskbars = find_taskbars(monitors)
        except Exception:
            taskbars = []
        return frame, virtual, monitors, taskbars

    def _finish_image(self, frame, virtual, monitors, taskbars, rect, when, label):
        """Crop `rect` from the frozen frame and attach the taskbar if enabled."""
        box = (rect["left"] - virtual["left"], rect["top"] - virtual["top"],
               rect["left"] - virtual["left"] + rect["width"],
               rect["top"] - virtual["top"] + rect["height"])
        img = frame if box == (0, 0, frame.width, frame.height) else frame.crop(box)
        if not self.include_taskbar.get():
            return img, label
        img, note = attach_taskbar(img, rect, frame, virtual, monitors, taskbars, when)
        if note == "taskbar added":
            label += " + taskbar"
        elif note.startswith("time stamp"):
            label += " + time stamp (taskbar hidden)"
        return img, label

    def _perform_capture(self):
        mode = self.mode.get()
        when = datetime.now().astimezone()
        stamp = when.strftime("%Y-%m-%d_%H-%M-%S")
        try:
            frame, virtual, monitors, taskbars = self._grab_frame()
            if mode == "region":
                self._region_overlay(stamp, when, frame, virtual, monitors, taskbars)
                return
            targets = []
            if mode == "screen":
                targets.append((virtual, "All-Screens", "All screens"))
            elif mode == "separate":
                for i, mon in enumerate(monitors, 1):
                    targets.append((mon, f"Display-{i}", f"Display {i}"))
            else:
                idx = self.selected_monitor_index
                if idx < 0 or idx >= len(monitors):
                    raise ValueError("Click a display in the monitor picker first.")
                targets.append((monitors[idx], f"Display-{idx+1}", f"Display {idx+1}"))
            saved = []
            for rect, file_label, label in targets:
                img, label = self._finish_image(frame, virtual, monitors, taskbars, rect, when, label)
                path = self._destination(stamp, file_label)
                img.save(path)
                saved.append((path, label))
            self._record_and_finish(saved, stamp, mode)
        except Exception as exc:
            self._from_hotkey = False
            self._restore_window()
            messagebox.showerror("Capture failed", str(exc))
            self.status.set("Capture failed. Please try again.")

    def _region_overlay(self, stamp, when, background, virtual, monitors, taskbars):

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{virtual['width']}x{virtual['height']}+{virtual['left']}+{virtual['top']}")
        canvas = tk.Canvas(overlay, cursor="crosshair", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        overlay.update_idletasks()

        dim = background.point(lambda p: int(p * 0.38))
        photo = ImageTk.PhotoImage(dim)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.image = photo
        canvas.create_text(virtual["width"] // 2, 34,
                           text="Drag to select an area   ·   Esc or right-click to cancel",
                           fill="white", font=("Segoe UI", 15, "bold"))

        rect = None
        start = [0, 0]

        def down(event):
            nonlocal rect
            start[:] = [event.x, event.y]
            if rect:
                canvas.delete(rect)
            rect = canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                           outline="#60a5fa", width=3,
                                           fill="#3b82f6", stipple="gray25")

        def move(event):
            if rect:
                canvas.coords(rect, start[0], start[1], event.x, event.y)

        def up(event):
            x1, y1 = min(start[0], event.x), min(start[1], event.y)
            x2, y2 = max(start[0], event.x), max(start[1], event.y)
            overlay.destroy()
            if x2 - x1 < 4 or y2 - y1 < 4:
                self._restore_window()
                self.status.set("Selection cancelled.")
                return
            region = {"left": virtual["left"] + x1, "top": virtual["top"] + y1,
                      "width": x2 - x1, "height": y2 - y1}
            try:
                # Crop from the frozen frame shown in the overlay (same instant as the
                # taskbar clock), rather than re-grabbing after the overlay closes.
                image, label = self._finish_image(background, virtual, monitors, taskbars,
                                                  region, when, "Selected region")
                path = self._destination(stamp, "Region")
                image.save(path)
                self._record_and_finish([(path, label)], stamp, "region")
            except Exception as exc:
                self._from_hotkey = False
                self._restore_window()
                messagebox.showerror("Capture failed", str(exc))

        def cancel(_event=None):
            try:
                overlay.destroy()
            except tk.TclError:
                pass
            self._restore_window()
            self.status.set("Selection cancelled.")

        canvas.bind("<ButtonPress-1>", down)
        canvas.bind("<B1-Motion>", move)
        canvas.bind("<ButtonRelease-1>", up)
        canvas.bind("<ButtonPress-3>", cancel)  # right-click also cancels
        overlay.bind("<Escape>", cancel)
        overlay.lift()
        overlay.focus_force()

    INDEX_FIELDS = ["captured_at_local", "work_type", "entity", "account", "period",
                    "reference", "notes", "capture_mode", "display_or_region",
                    "file_name", "relative_path"]

    def _write_index_row(self, row: dict | None = None) -> bool:
        """Append a row to evidence_index.csv (plus any rows still waiting for this folder).

        If the index can't be written (typically because it's open in Excel), the row is
        kept in settings and written the next time the file is free. Captures never fail
        because of the index.
        """
        root = Path(self.save_folder.get()).expanduser()
        pending = [p for p in self.settings.get("pending_index", []) if isinstance(p, dict)]
        mine = [p for p in pending if self._same_folder(str(p.get("folder", "")), str(root))]
        rows = [p.get("row", {}) for p in mine] + ([row] if row else [])
        if not rows:
            return True
        try:
            root.mkdir(parents=True, exist_ok=True)
            index = root / "evidence_index.csv"
            exists = index.exists()
            with index.open("a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=self.INDEX_FIELDS, extrasaction="ignore")
                if not exists:
                    writer.writeheader()
                writer.writerows(rows)
        except OSError:
            if row:
                pending.append({"folder": str(root), "row": row})
                self.settings["pending_index"] = pending
                save_settings(self.settings)
            self._index_waiting = True
            return False
        if mine:
            self.settings["pending_index"] = [p for p in pending if p not in mine]
            save_settings(self.settings)
        return True

    def _remove_index_rows(self, names: set[str]) -> None:
        """Take rows for the given file names back out of the index (used by Undo)."""
        root = Path(self.save_folder.get()).expanduser()
        pending = self.settings.get("pending_index", [])
        kept = [p for p in pending if p.get("row", {}).get("file_name") not in names]
        if len(kept) != len(pending):
            self.settings["pending_index"] = kept
            save_settings(self.settings)
        index = root / "evidence_index.csv"
        try:
            with index.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames or self.INDEX_FIELDS
                rows = list(reader)
            remaining = [r for r in rows if r.get("file_name") not in names]
            if len(remaining) == len(rows):
                return
            tmp = index.with_suffix(".tmp")
            with tmp.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(remaining)
            tmp.replace(index)
        except OSError:
            pass  # index missing or open elsewhere; the files themselves are still removed

    def _index_marked_copy(self, original: Path, marked: Path):
        """Add an index row for a marked-up copy, reusing the original's workpaper labels."""
        root = Path(self.save_folder.get()).expanduser()
        base = None
        try:
            with (root / "evidence_index.csv").open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if row.get("file_name") == original.name:
                        base = row  # keep the latest match
        except OSError:
            pass
        row = dict(base or {"work_type": "", "entity": self.entity.get().strip(),
                            "account": self.account.get().strip(), "period": self.period.get().strip(),
                            "reference": self.reference.get().strip(), "notes": "",
                            "capture_mode": ""})
        row.update(
            captured_at_local=datetime.now().astimezone().isoformat(timespec="seconds"),
            display_or_region=f"Marked-up copy of {original.name}",
            file_name=marked.name,
            relative_path=str(marked.relative_to(root)) if marked.is_relative_to(root) else str(marked),
        )
        self._write_index_row(row)

    def _append_index(self, path: Path, capture_label: str, stamp: str, mode: str):
        root = Path(self.save_folder.get()).expanduser()
        row = {
            "captured_at_local": datetime.now().astimezone().isoformat(timespec="seconds"),
            "work_type": "",  # column kept so existing evidence_index.csv files stay aligned
            "entity": self.entity.get().strip(),
            "account": self.account.get().strip(),
            "period": self.period.get().strip(),
            "reference": self.reference.get().strip(),
            "notes": "",  # Note field removed; column kept so older index files line up
            "capture_mode": mode,
            "display_or_region": capture_label,
            "file_name": path.name,
            "relative_path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
        }
        self._write_index_row(row)

    def _record_and_finish(self, saved, stamp, mode):
        self._index_waiting = False
        self._remember_folder(self.save_folder.get())
        self._remember_labels()
        self._persist()
        for path, label in saved:
            self._append_index(path, label, stamp, mode)
        self.refresh_history()
        if self.markup_after.get() and len(saved) == 1:
            original = saved[0][0]
            self.status.set("Saved. Mark it up, or press Esc to skip.")
            try:
                MarkupEditor(self.root, original, lambda marked: self._complete(saved, marked))
                return
            except Exception:
                pass  # couldn't open the editor; finish normally
        self._complete(saved, None)

    def _copy_file_to_clipboard(self, path: Path | None) -> bool:
        if path is None or not self.copy_clipboard.get():
            return False
        try:
            with Image.open(path) as im:
                return copy_image_to_clipboard(im)
        except Exception:
            return False

    def _index_note(self) -> str:
        if getattr(self, "_index_waiting", False):
            return "\nevidence_index.csv is open in another program; it will be updated once you close it."
        return ""

    def _complete(self, saved, marked: Path | None):
        """Final step after a capture (and optional markup). Never interrupts with a dialog."""
        if marked:
            self._index_marked_copy(saved[0][0], marked)
        originals = [p for p, _ in saved]
        files = originals + ([marked] if marked else [])
        final = marked or (originals[0] if len(originals) == 1 else None)
        copied = self._copy_file_to_clipboard(final)

        self._restore_window()
        self.refresh_history()
        if final is not None:
            title = "✓ Saved and copied. Paste with Ctrl+V" if copied else "✓ Saved"
            detail = final.name + ("\nOriginal kept alongside it." if marked else "")
        else:
            title = f"✓ {len(saved)} screenshots saved"
            detail = "One per display." + (" Not copied: select one below to copy it."
                                           if self.copy_clipboard.get() else "")
        detail += self._index_note()
        self.status.set(title.lstrip("✓ ") + "  ·  " + (final.name if final else f"{len(saved)} files"))
        if self.open_after.get() and final is not None:
            self._open_path(final)

        actions = []
        if final is not None and not marked:
            actions.append(("🖍 Mark up", lambda: self._markup(final)))
        actions.append(("Show in folder", lambda: self._show_in_folder(final or originals[0])))
        actions.append(("Undo", lambda: self._undo_capture(files)))
        self._show_toast(title, detail, final or originals[0], actions)
        self._from_hotkey = False

    def _markup(self, original: Path):
        """Open the markup window for a saved screenshot; the original is never changed."""

        def done(marked):
            if not marked:
                return
            self._index_waiting = False
            self._index_marked_copy(original, marked)
            self.refresh_history()
            copied = self._copy_file_to_clipboard(marked)
            title = "✓ Marked copy saved and copied. Paste with Ctrl+V" if copied else "✓ Marked copy saved"
            self.status.set(title.lstrip("✓ ") + "  ·  " + marked.name)
            self._show_toast(title, marked.name + "\nOriginal kept alongside it." + self._index_note(), marked,
                             [("Show in folder", lambda: self._show_in_folder(marked)),
                              ("Undo", lambda: self._undo_capture([marked]))])

        try:
            MarkupEditor(self.root, original, done)
        except Exception as exc:
            messagebox.showerror("Couldn't open image", str(exc))

    def markup_selected(self):
        original = self._selected_path()
        if original is not None:
            self._markup(original)

    def _undo_capture(self, files):
        """Delete the screenshot(s) just saved and take them back out of the index."""
        removed = 0
        for path in files:
            try:
                Path(path).unlink()
                removed += 1
            except OSError:
                pass
        self._remove_index_rows({Path(f).name for f in files})
        self.refresh_history()
        text = "Capture removed" if removed else "Nothing to undo"
        self.status.set(text + ".")
        self._show_toast("↶ " + text, seconds=2.5)

    def _show_in_folder(self, path: Path):
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            self._open_path(Path(path).parent)

    def _open_path(self, path: Path):
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Couldn't open file", str(exc))

    def open_folder(self):
        folder = Path(self.save_folder.get()).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        self._open_path(folder)

    def refresh_history(self):
        self.history.delete(0, tk.END)
        folder = Path(self.save_folder.get()).expanduser()
        self.history_paths = []
        if folder.exists():
            self.history_paths = sorted(folder.rglob("*.png"),
                                        key=lambda p: p.stat().st_mtime, reverse=True)[:12]
        for path in self.history_paths:
            when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%b %d, %I:%M %p")
            mark = "🖍 " if "_marked" in path.stem else "    "
            self.history.insert(tk.END, f" {mark}{when}    ·    {path.name}")
        if not self.history_paths:
            self.history.insert(tk.END, "  Nothing here yet. Your captures will appear in this list.")
            self.history.itemconfigure(0, fg=MUTED)
        if self.history_paths:
            self.history.selection_set(0)
        self._update_history_buttons()

    def _update_preview(self):
        path = self._selected_path()
        photo = None
        if path is not None:
            try:
                with Image.open(path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((214, 112))
                    photo = ImageTk.PhotoImage(im)
            except Exception:
                photo = None
        self.preview.image = photo
        self.preview.configure(image=photo or "", text="" if photo else "No preview")

    def _selected_path(self) -> Path | None:
        selection = self.history.curselection()
        if selection and selection[0] < len(self.history_paths):
            return self.history_paths[selection[0]]
        return None

    def open_selected(self, _event=None):
        path = self._selected_path()
        if path:
            self._open_path(path)

    def copy_selected(self):
        path = self._selected_path()
        if not path:
            return
        try:
            with Image.open(path) as im:
                ok = copy_image_to_clipboard(im)
        except Exception:
            ok = False
        self.status.set(f"Copied {path.name}. Paste with Ctrl+V." if ok else "Couldn't copy to the clipboard.")

    def show_selected(self):
        path = self._selected_path()
        if path:
            self._show_in_folder(path)


def main():
    root = tk.Tk()
    SnapShotterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
