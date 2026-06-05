"""
camera_tab.py - Tab for viewing the drone's camera feed embedded in the GUI.

Listens on UDP port 5600 for the H.264 RTP stream that GstCameraPlugin
in iris_camera_sonar (and similar models) publishes when streaming is
enabled. Decodes it and renders directly into a tkinter Frame by handing
the frame's X11 window-id to xvimagesink or ximagesink.

Sink fallback chain:
  1. xvimagesink — fastest, uses XVideo overlay. Often unavailable on
     VirtualBox / VMWare guests because the virtual GPU driver doesn't
     expose Xv adapters. In that case set_state(PLAYING) returns FAILURE
     immediately. We drain the bus to log the real error, then try...
  2. ximagesink — pure X11 blitting via XPutImage. CPU-bound and slower
     but works on every X11 display, including VMs without Xv.

Both honor GstVideoOverlay.set_window_handle, so the video stays inside
our tk frame either way.

On Start, we best-effort poke /drone/camera/enable_streaming with `true`
so models that gate on that topic begin sending. Models without the
topic ignore the poke.

Requirements (Ubuntu/Debian) — install once with:
    sudo apt install -y python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 \\
        gstreamer1.0-tools gstreamer1.0-plugins-good \\
        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \\
        gstreamer1.0-libav

If python3-gi isn't installed the tab still loads cleanly and shows the
install command in its placeholder text instead of crashing the GUI.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
from typing import Optional

from .global_state import GlobalState
from .theme import get_terminal_colors, COLORS


# ── GStreamer Python bindings (gracefully optional) ──
GST_AVAILABLE = False
GST_IMPORT_ERROR = ''
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstVideo', '1.0')
    from gi.repository import Gst, GstVideo  # noqa: F401
    Gst.init(None)
    GST_AVAILABLE = True
except Exception as _e:
    GST_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"


RTP_CAPS = (
    'application/x-rtp,'
    'media=(string)video,'
    'clock-rate=(int)90000,'
    'encoding-name=(string)H264'
)

DEFAULT_UDP_PORT = 5600
DEFAULT_ENABLE_TOPIC = '/drone/camera/enable_streaming'

# Ordered list of sink configurations to try. First success wins.
# Both elements honor set_window_handle for tk embedding.
SINK_CANDIDATES = [
    ('xvimagesink',
     'xvimagesink name=videosink sync=false force-aspect-ratio=true'),
    ('ximagesink',
     'ximagesink name=videosink sync=false force-aspect-ratio=true'),
]


class CameraTab(ttk.Frame):
    """Tab that displays the live H.264 video feed inline."""

    def __init__(self, parent, state: GlobalState):
        super().__init__(parent, padding="10")
        self.state = state

        self.pipeline = None                   # type: Optional[object]
        self._bus_poll_id: Optional[str] = None
        self._active_sink: Optional[str] = None  # name of sink in use

        self.setup_gui()

    # ====================================================================== GUI
    def setup_gui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Top control bar ──
        ctrl = ttk.Frame(self)
        ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.start_btn = ttk.Button(
            ctrl, text="▶  Start Stream",
            command=self.start_stream,
            style='Accent.TButton',
            state='normal' if GST_AVAILABLE else 'disabled')
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(
            ctrl, text="⏹  Stop",
            command=self.stop_stream, state='disabled',
            style='Danger.TButton')
        self.stop_btn.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Separator(ctrl, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Label(ctrl, text="UDP port:").pack(side=tk.LEFT)
        self.port_var = tk.IntVar(value=DEFAULT_UDP_PORT)
        ttk.Spinbox(ctrl, from_=1024, to=65535, width=7,
                    textvariable=self.port_var).pack(side=tk.LEFT, padx=(5, 15))

        ttk.Label(ctrl, text="Enable topic:").pack(side=tk.LEFT)
        self.topic_var = tk.StringVar(value=DEFAULT_ENABLE_TOPIC)
        ttk.Entry(ctrl, textvariable=self.topic_var, width=32).pack(
            side=tk.LEFT, padx=(5, 15))

        self.status_var = tk.StringVar(value="Idle")
        self.status_label = ttk.Label(
            ctrl, textvariable=self.status_var,
            style='StatusGray.TLabel')
        self.status_label.pack(side=tk.RIGHT)
        ttk.Label(ctrl, text="Status:").pack(side=tk.RIGHT, padx=(0, 5))

        # ── Main content: video on top, log on bottom ──
        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=3)
        content.rowconfigure(1, weight=1)

        video_outer = ttk.LabelFrame(content, text="Camera Feed", padding=2)
        video_outer.grid(row=0, column=0, sticky="nsew")
        video_outer.columnconfigure(0, weight=1)
        video_outer.rowconfigure(0, weight=1)

        self.video_frame = tk.Frame(video_outer, bg='black',
                                    width=1280, height=720,
                                    highlightthickness=0, bd=0)
        self.video_frame.grid(row=0, column=0, sticky="nsew")
        self.video_frame.grid_propagate(False)

        if GST_AVAILABLE:
            placeholder = (
                "No stream active.\n\n"
                "Click ▶ Start Stream to receive H.264 video on UDP "
                f"port {DEFAULT_UDP_PORT}.\n\n"
                "(Launch a simulation with a camera-equipped drone, e.g.\n"
                "'Sensor Test' or 'Plains Iris Gimbal Camera', then come back.)")
        else:
            placeholder = (
                "GStreamer Python bindings not available.\n\n"
                f"Import failed:\n  {GST_IMPORT_ERROR}\n\n"
                "Install with:\n"
                "  sudo apt install -y python3-gi python3-gi-cairo "
                "gir1.2-gstreamer-1.0\n\n"
                "Then restart the GUI.")
        self._placeholder = tk.Label(
            self.video_frame, text=placeholder, bg='black', fg='#888',
            font=('Segoe UI', 11), justify=tk.CENTER)
        self._placeholder.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        log_frame = ttk.LabelFrame(content, text="Camera Log", padding="6")
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        tc = get_terminal_colors()
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=6, font=('Consolas', 9), state='disabled',
            bg=tc['bg'], fg=tc['fg'],
            selectbackground=tc['select_bg'],
            selectforeground=tc['select_fg'],
            insertbackground=tc['fg'],
            relief='flat', borderwidth=0)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        ttk.Button(log_frame, text="Clear Log",
                   command=self.clear_log).grid(row=1, column=0, sticky="e", pady=(4, 0))

        if not GST_AVAILABLE:
            self.log("[WARN] python3-gi missing — install with apt to enable streaming.")
        else:
            self.log("[INFO] Camera tab ready. GStreamer version: "
                     f"{Gst.version_string()}")

    # ============================================================== Start / Stop
    def start_stream(self):
        if not GST_AVAILABLE:
            self.log("[ERROR] GStreamer Python bindings not available.")
            return
        if self.pipeline is not None:
            self.log("[INFO] Stream already running.")
            return

        try:
            port = int(self.port_var.get())
        except (tk.TclError, ValueError):
            port = DEFAULT_UDP_PORT
            self.port_var.set(port)

        topic = self.topic_var.get().strip() or DEFAULT_ENABLE_TOPIC

        threading.Thread(
            target=self._poke_enable_streaming,
            args=(topic,),
            daemon=True).start()

        self._placeholder.place_forget()
        self.video_frame.update_idletasks()
        win_id = self.video_frame.winfo_id()

        if not win_id:
            self.log("[ERROR] Video frame has no X11 window id — tab not visible?")
            self._set_status("Error", error=True)
            self._placeholder.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            return

        # Try each sink in order. First one to reach PLAYING wins.
        last_error = None
        for sink_name, sink_str in SINK_CANDIDATES:
            pipeline_str = (
                f'udpsrc port={port} caps="{RTP_CAPS}" ! '
                'rtpjitterbuffer latency=50 drop-on-latency=true ! '
                'rtph264depay ! '
                'avdec_h264 ! '
                'videoconvert ! '
                f'{sink_str}'
            )
            self.log(f"[TRY] {sink_name}")

            try:
                pipeline = Gst.parse_launch(pipeline_str)
            except Exception as e:
                last_error = f"parse_launch: {e}"
                self.log(f"[FAIL] {sink_name}: {last_error}")
                continue

            # Bind sync bus before any state change so we can answer
            # prepare-window-handle the moment xvimagesink/ximagesink asks.
            bus = pipeline.get_bus()
            bus.enable_sync_message_emission()
            bus.connect('sync-message::element', self._on_sync_message, win_id)

            ret = pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                errors = self._drain_bus_errors(bus)
                detail = ('; '.join(errors) if errors
                          else 'set_state FAILURE with no message on bus')
                last_error = detail
                self.log(f"[FAIL] {sink_name}: {detail}")
                try:
                    pipeline.set_state(Gst.State.NULL)
                except Exception:
                    pass
                continue

            # Success.
            self.pipeline = pipeline
            self._active_sink = sink_name
            self._bus_poll_id = self.after(100, self._poll_bus)
            self._set_status(f"Streaming ({sink_name})", running=True)
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.log(f"[START] {sink_name} on UDP {port}")
            self.log(f"[PIPELINE] {pipeline_str}")
            return

        # All sinks failed.
        self.log(f"[ERROR] No usable video sink. Last error: {last_error}")
        self.log("[HINT] Run 'gst-launch-1.0 videotestsrc ! ximagesink' "
                 "to verify GStreamer can render at all.")
        self._set_status("No sink available", error=True)
        self._placeholder.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _drain_bus_errors(self, bus) -> list:
        """Pop all error/warning messages currently on bus, return as strings."""
        out = []
        for _ in range(20):  # safety cap
            msg = bus.timed_pop_filtered(
                0,
                Gst.MessageType.ERROR | Gst.MessageType.WARNING)
            if msg is None:
                break
            try:
                if msg.type == Gst.MessageType.ERROR:
                    err, debug = msg.parse_error()
                    out.append(f"ERROR: {err.message}")
                    if debug:
                        out.append(f"DEBUG: {debug.splitlines()[0]}")
                else:
                    warn, _ = msg.parse_warning()
                    out.append(f"WARN: {warn.message}")
            except Exception as e:
                out.append(f"(parse failed: {e})")
        return out

    def _poke_enable_streaming(self, topic: str):
        """Best-effort send of `data: true` to enable_streaming on `topic`."""
        try:
            result = subprocess.run(
                ['gz', 'topic', '-t', topic,
                 '-m', 'gz.msgs.Boolean', '-p', 'data: true'],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.after(0, lambda: self.log(f"[STREAM] Enabled {topic}"))
            else:
                first_line = (result.stderr or result.stdout or '').strip().splitlines()
                detail = first_line[0] if first_line else f"exit {result.returncode}"
                self.after(0, lambda d=detail: self.log(
                    f"[STREAM] enable_streaming poke skipped ({d})"))
        except subprocess.TimeoutExpired:
            self.after(0, lambda: self.log(
                "[STREAM] enable_streaming poke timed out (Gazebo not running?)"))
        except FileNotFoundError:
            self.after(0, lambda: self.log(
                "[STREAM] 'gz' not on PATH — skipping enable poke"))
        except Exception as e:
            self.after(0, lambda e=e: self.log(
                f"[STREAM] enable_streaming poke failed: {e}"))

    def _on_sync_message(self, bus, msg, win_id):
        """Sync bus callback — called from a GStreamer thread."""
        try:
            structure = msg.get_structure()
            if structure is None:
                return
            if structure.get_name() == 'prepare-window-handle':
                msg.src.set_window_handle(win_id)
        except Exception:
            pass

    def _poll_bus(self):
        """Poll the GStreamer bus from tk's main loop for non-sync messages."""
        if self.pipeline is None:
            self._bus_poll_id = None
            return

        bus = self.pipeline.get_bus()
        msg_types = (Gst.MessageType.ERROR
                     | Gst.MessageType.EOS
                     | Gst.MessageType.WARNING)

        while True:
            msg = bus.timed_pop_filtered(0, msg_types)
            if msg is None:
                break
            t = msg.type
            if t == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                self.log(f"[GST ERROR] {err.message}")
                if debug:
                    self.log(f"[GST DEBUG] {debug.splitlines()[0]}")
                self._cleanup_pipeline()
                self._set_status("Error", error=True)
                self.start_btn.config(state='normal')
                self.stop_btn.config(state='disabled')
                self._placeholder.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
                return
            elif t == Gst.MessageType.EOS:
                self.log("[GST] End-of-stream")
                self._cleanup_pipeline()
                self._set_status("Idle")
                self.start_btn.config(state='normal')
                self.stop_btn.config(state='disabled')
                self._placeholder.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
                return
            elif t == Gst.MessageType.WARNING:
                warn, _ = msg.parse_warning()
                self.log(f"[GST WARN] {warn.message}")

        self._bus_poll_id = self.after(200, self._poll_bus)

    def stop_stream(self):
        if self.pipeline is None:
            return
        self.log("[STOP] Stopping stream")
        self._cleanup_pipeline()
        self._set_status("Idle")
        self.start_btn.config(state='normal' if GST_AVAILABLE else 'disabled')
        self.stop_btn.config(state='disabled')
        self._placeholder.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _cleanup_pipeline(self):
        if self.pipeline is not None:
            try:
                self.pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
            self.pipeline = None
        self._active_sink = None
        if self._bus_poll_id is not None:
            try:
                self.after_cancel(self._bus_poll_id)
            except Exception:
                pass
            self._bus_poll_id = None

    def destroy(self):
        """Clean shutdown when the tab / app is destroyed."""
        self._cleanup_pipeline()
        super().destroy()

    # ============================================================== UI Helpers
    def _set_status(self, text: str, running: bool = False, error: bool = False):
        self.status_var.set(text)
        if error:
            self.status_label.config(style='StatusRed.TLabel')
        elif running:
            self.status_label.config(style='StatusGreen.TLabel')
        else:
            self.status_label.config(style='StatusGray.TLabel')

    def log(self, message: str):
        def _log():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, message + '\n')
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        self.after(0, _log)

    def clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')