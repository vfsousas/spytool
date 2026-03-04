import base64
import io
import json
import tempfile
from time import sleep
from flask import Flask, render_template, request, jsonify, url_for, Response
import os
import webbrowser
import re
import subprocess
import logging
import socket
import time
from parse_pywinauto import Parser

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    OPENCV_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PyAutoGUI not available: {e}")
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

try:
    from lvgl_inspector import LVGLInspector, ScreenshotBackend
    LVGL_AVAILABLE = True
except ImportError:
    LVGLInspector = None
    ScreenshotBackend = None
    LVGL_AVAILABLE = False
    logger.warning("LVGL inspector not available.")

app = Flask(__name__, template_folder="routes")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _img_to_b64(img_path: str) -> str:
    """Read a saved image file and return base64-encoded PNG string."""
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _ndarray_to_b64(img) -> str:
    """Encode an OpenCV numpy array to base64 PNG."""
    tmp = os.path.join(tempfile.gettempdir(), "_spytool_enc.png")
    ScreenshotBackend.save_annotated(img, tmp)
    data = _img_to_b64(tmp)
    try:
        os.remove(tmp)
    except Exception:
        pass
    return data


def open_browser():
    webbrowser.open("http://127.0.0.1:5050/")


def _qemu_png_output_path() -> str:
    return os.path.join(app.static_folder, "img", "qemu_screenshot.png")


def _qemu_png_url():
    path = _qemu_png_output_path()
    if not os.path.exists(path):
        return None
    return url_for("static", filename="img/qemu_screenshot.png", v=int(os.path.getmtime(path)))


def capture_qemu_monitor_screendump_base64(
    host: str = "127.0.0.1",
    port: int = 55555,
    ppm_path: str = "/tmp/screenshot.ppm",
    output_png: str = None,
    timeout: float = 5.0,
) -> str:
    """
    Use QEMU monitor TCP to run `screendump`, convert the PPM to PNG, and return PNG as base64.
    """
    output_png = output_png or _qemu_png_output_path()
    os.makedirs(os.path.dirname(output_png), exist_ok=True)

    with socket.create_connection((host, int(port)), timeout=timeout) as sock:
        sock.settimeout(timeout)
        try:
            sock.recv(4096)
        except Exception:
            pass
        sock.sendall(f"screendump {ppm_path}\n".encode("utf-8"))
        end_time = time.time() + timeout
        buffer = b""
        while time.time() < end_time:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                if b"(qemu)" in buffer:
                    break
            except socket.timeout:
                break

    if not os.path.exists(ppm_path):
        raise RuntimeError(f"QEMU screendump did not create: {ppm_path}")

    try:
        from PIL import Image
        with Image.open(ppm_path) as img:
            img.save(output_png, format="PNG")
    except Exception as exc:
        raise RuntimeError(f"Failed to convert PPM to PNG: {exc}") from exc

    return _img_to_b64(output_png)


def getWindows():
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        return [w.title for w in windows if w.title.strip() and not w.title.startswith("Program Manager")]
    except Exception as e:
        logger.error(f"Error getting windows: {e}")
        return []


def printscreen(region=None):
    if not PYAUTOGUI_AVAILABLE:
        raise ImportError("PyAutoGUI is not available.")
    screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
    buf = io.BytesIO()
    screenshot.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def capture_window_by_title_base64(title_keywords):
    if not PYAUTOGUI_AVAILABLE:
        raise RuntimeError("PyAutoGUI not available.")
    if os.name != "nt":
        raise RuntimeError("Window-title fallback is only supported on Windows.")
    else:
        import pygetwindow as gw

        windows = gw.getAllWindows()
        keywords = [k.lower() for k in title_keywords if k]
        matches = []
        for w in windows:
            title = (w.title or "").strip()
            if not title:
                continue
            lower = title.lower()
            if any(k in lower for k in keywords):
                matches.append(w)

        if not matches:
            raise RuntimeError("No matching local QEMU window found for fallback capture.")

        target = matches[0]
        left, top, width, height = target.left, target.top, target.width, target.height
        if width <= 0 or height <= 0:
            raise RuntimeError("Matched QEMU window has invalid dimensions for capture.")
        return printscreen(region=(int(left), int(top), int(width), int(height)))


def capture_linux_window_by_title_base64(title_keywords):
    if not PYAUTOGUI_AVAILABLE:
        raise RuntimeError("PyAutoGUI not available.")
    if os.name == "nt":
        raise RuntimeError("Linux window fallback requested on Windows.")
    window_ids = []
    qemu_pids = []
    try:
        pid_proc = subprocess.run(["pgrep", "-f", "qemu-system"], capture_output=True, text=True)
        if pid_proc.returncode == 0:
            qemu_pids = [p.strip() for p in pid_proc.stdout.splitlines() if p.strip()]
    except FileNotFoundError:
        pass
    for pid in qemu_pids:
        try:
            proc = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", pid], capture_output=True, text=True)
            if proc.returncode == 0:
                window_ids.extend([l.strip() for l in proc.stdout.splitlines() if l.strip()])
        except FileNotFoundError as exc:
            raise RuntimeError("xdotool not installed.") from exc
    for kw in title_keywords:
        if not kw:
            continue
        try:
            proc = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", kw], capture_output=True, text=True)
            if proc.returncode == 0:
                window_ids.extend([l.strip() for l in proc.stdout.splitlines() if l.strip()])
        except FileNotFoundError as exc:
            raise RuntimeError("xdotool not installed.") from exc
    if not window_ids:
        raise RuntimeError("No matching Linux QEMU window found via xdotool.")
    for wid in reversed(window_ids):
        try:
            xwd = subprocess.run(["xwd", "-id", wid, "-silent"], capture_output=True, timeout=5)
            if xwd.returncode != 0 or not xwd.stdout:
                continue
            conv = subprocess.run(["convert", "xwd:-", "png:-"], input=xwd.stdout, capture_output=True, timeout=5)
            if conv.returncode == 0 and conv.stdout:
                return base64.b64encode(conv.stdout).decode("utf-8")
        except Exception:
            continue
    raise RuntimeError("Failed to capture Linux QEMU window.")


def parse_screen_position(text):
    match = re.search(r"\(L(-?\d+), T(-?\d+), R(-?\d+), B(-?\d+)\)", text)
    if match:
        l, t, r, b = match.groups()
        return {"left": int(l), "top": int(t), "right": int(r), "bottom": int(b)}
    return None


def parse_auto_id(text):
    m = re.search(r'auto_id="([^"]+)"', text)
    return m.group(1) if m else None


def parse_title(text):
    m = re.search(r'title="([^"]+)"', text)
    return m.group(1) if m else None


def parse_control_type(text):
    m = re.search(r'control_type="([^"]+)"', text)
    return m.group(1) if m else None


def find_node_by_idx(node, target_idx):
    if node["idx"] == target_idx:
        return node
    for child in node.get("children", []):
        r = find_node_by_idx(child, target_idx)
        if r:
            return r
    return None


def _rect_to_window_dict(rect):
    return {"left": int(rect.left), "top": int(rect.top), "right": int(rect.right), "bottom": int(rect.bottom)}


def _encode_pil_image(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _inspect_with_pywinauto(window_title):
    from pywinauto import Desktop
    from pywinauto.application import Application
    desktop = Desktop(backend="uia")
    matches = [w for w in desktop.windows() if window_title.lower() in w.window_text().lower()]
    if not matches:
        raise ValueError("Window not found")
    target_wrapper = matches[0]
    handle = target_wrapper.handle
    app = Application(backend="uia").connect(handle=handle, timeout=5)
    target = app.window(handle=handle)
    try:
        if hasattr(target_wrapper, "is_minimized") and target_wrapper.is_minimized():
            target_wrapper.restore()
        target.set_focus()
        sleep(0.3)
    except Exception as exc:
        logger.warning(f"Could not focus target window: {exc}")
    temp_directory = tempfile.gettempdir()
    dump_file = os.path.join(temp_directory, "pywinauto_dump.txt")
    target.print_control_identifiers(filename=dump_file)
    tree = Parser().parse(dump_file)
    if not tree:
        raise RuntimeError("No UI tree parsed from pywinauto output.")
    screenshot_b64 = ""
    try:
        screenshot_b64 = _encode_pil_image(target.capture_as_image())
    except Exception as exc:
        logger.warning(f"Window capture failed, trying pyautogui: {exc}")
        if PYAUTOGUI_AVAILABLE:
            rect = target_wrapper.rectangle()
            screenshot_b64 = printscreen(region=(int(rect.left), int(rect.top), max(int(rect.width()), 1), max(int(rect.height()), 1)))
    if not screenshot_b64:
        raise RuntimeError("Failed to capture screenshot for selected window.")
    return tree, screenshot_b64, _rect_to_window_dict(target_wrapper.rectangle())


# ─────────────────────────────────────────────
# Routes — desktop inspector
# ─────────────────────────────────────────────

@app.route("/")
def index():
    try:
        return render_template(
            "index.html",
            windows_list=getWindows(),
            qemu_image_url=_qemu_png_url(),
        )
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


@app.route("/element/<idx>", methods=["GET"])
def element(idx):
    try:
        temp_directory = tempfile.gettempdir()
        temp_file = os.path.join(temp_directory, "parsed_pywinauto.json")
        if not os.path.exists(temp_file):
            temp_file = os.path.join(temp_directory, "parsed_opencv.json")
        with open(temp_file) as f:
            data = json.load(f)
        node = find_node_by_idx(data, int(idx))
        return jsonify(node)
    except FileNotFoundError:
        return jsonify({"error": "Parsed file not found"}), 404
    except Exception as e:
        logger.error(f"Error retrieving element: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/inspect/<path:window>", methods=["GET"])
def inspect(window):
    try:
        tree, screenshot_b64, window_rect = _inspect_with_pywinauto(window)
        temp_file = os.path.join(tempfile.gettempdir(), "parsed_pywinauto.json")
        with open(temp_file, "w") as f:
            json.dump(tree, f)
        return jsonify({"printscreen": screenshot_b64, "tree": tree, "window_rect": window_rect})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Desktop inspection failed: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# Routes — LVGL inspector
# ─────────────────────────────────────────────

@app.route("/lvgl/inspect", methods=["POST"])
def lvgl_inspect():
    """Return the LVGL widget tree as a structured JSON object."""
    if not LVGL_AVAILABLE:
        return jsonify({"error": "LVGL Inspector not available. Required packages not installed."}), 500
    try:
        # Get parameters from the request
        data = request.json
        element = data.get("element", "root")
        max_depth = data.get("max_depth", None)
        ip = data.get("ip", "192.168.0.10")
        port = data.get("port", 8080)
        capture = data.get("capture", "none")
        vnc_host = data.get("vnc_host", "192.168.0.10")
        vnc_port = data.get("vnc_port", 5900)
        snapshot_path = data.get("snapshot_path", "/tmp/lvgl_snapshot.png")
        topic = data.get("topic", "receive-test-queries")
        username = data.get("username", "test-client")
        password = data.get("password", "test-client")
        deep_scan = data.get("deep_scan", True)
        scan_hidden = data.get("scan_hidden", True)
        scan_extra_roots = data.get("scan_extra_roots", True)

        inspector = LVGLInspector()
        tree_data = inspector.lvgl_application_structure(
            element=data.get("element", "root"),
            max_depth=data.get("max_depth", None),
            show_props=True,
            show_text=True,
            ip=data.get("ip", "192.168.0.10"),
            port=data.get("port", 8080),
            topic=data.get("topic", "receive-test-queries"),
            username=data.get("username", "test-client"),
            password=data.get("password", "test-client"),
            capture="none",   # screenshot is handled by /lvgl/screenshot
            deep_scan=data.get("deep_scan", True),
            scan_hidden=data.get("scan_hidden", True),
            scan_extra_roots=data.get("scan_extra_roots", True),
        )
        return jsonify({"tree": tree_data})
    except Exception as e:
        logger.error(f"LVGL inspection error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/lvgl/screenshot", methods=["POST"])
def lvgl_screenshot():
    """
    Capture a screenshot of the running QEMU image.

    Supported capture values:
      qemu_monitor  -> QEMU HMP monitor TCP using `screendump` (default)
      vnc           -> VNC snapshot (requires LVGL optional deps)
      x11           -> X11 root window dump (requires LVGL optional deps)
      framebuffer   -> /dev/fb0 raw read (requires LVGL optional deps)
      none          -> return empty immediately

    Fallbacks for qemu_monitor: QMP socket -> OS window capture.
    """
    try:
        data = request.get_json(silent=True) or {}
        capture_method = data.get("capture", "qemu_monitor")
        vnc_host = data.get("vnc_host", "192.168.0.10")
        vnc_port = data.get("vnc_port", 5900)
        qemu_monitor_host = data.get("qemu_monitor_host", "127.0.0.1")
        qemu_monitor_port = data.get("qemu_monitor_port", 55555)
        qemu_qmp_socket = data.get("qemu_qmp_socket", "/tmp/qemu.sock")
        fb_device = data.get("fb_device", "/dev/fb0")
        qemu_titles = data.get("qemu_window_titles", ["qemu", "qemu-system", "qemu-system-x86_64"])

        if capture_method == "none":
            return jsonify({"screenshot": ""})

        if capture_method == "x11":
            if not LVGL_AVAILABLE:
                return jsonify({"error": "LVGL Inspector not available for x11 capture."}), 500
            img = ScreenshotBackend.capture_x11()
            return jsonify({"screenshot": _ndarray_to_b64(img)})

        if capture_method == "framebuffer":
            if not LVGL_AVAILABLE:
                return jsonify({"error": "LVGL Inspector not available for framebuffer capture."}), 500
            img = ScreenshotBackend.capture_framebuffer(fb_device)
            return jsonify({"screenshot": _ndarray_to_b64(img)})

        if capture_method == "qemu_monitor":
            try:
                b64 = capture_qemu_monitor_screendump_base64(
                    host=qemu_monitor_host,
                    port=int(qemu_monitor_port),
                    ppm_path=data.get("qemu_screendump_path", "/tmp/screenshot.ppm"),
                    output_png=_qemu_png_output_path(),
                )
                return jsonify({"screenshot": b64, "image_url": _qemu_png_url()})
            except Exception as mon_err:
                logger.warning(f"QEMU monitor screendump failed: {mon_err}")
                if not LVGL_AVAILABLE:
                    return jsonify({
                        "error": (
                            f"QEMU monitor screendump failed: {mon_err}. "
                            "Install LVGL optional dependencies for extra fallbacks."
                        )
                    }), 500
                try:
                    img = ScreenshotBackend.capture_qemu_qmp(socket_path=qemu_qmp_socket)
                    return jsonify({"screenshot": _ndarray_to_b64(img), "fallback": "qemu_qmp"})
                except Exception as qmp_err:
                    logger.warning(f"QMP fallback failed: {qmp_err}")
                    try:
                        if os.name == "nt":
                            b64 = capture_window_by_title_base64(qemu_titles)
                        else:
                            b64 = capture_linux_window_by_title_base64(qemu_titles)
                        return jsonify({"screenshot": b64, "fallback": "qemu_window_only"})
                    except Exception as win_err:
                        return jsonify({
                            "error": (
                                f"QEMU Monitor failed: {mon_err}. "
                                f"QMP failed: {qmp_err}. "
                                f"Window fallback failed: {win_err}. "
                                "Make sure QEMU is running with: "
                                "-monitor tcp:127.0.0.1:55555,server,nowait"
                            )
                        }), 500

        if capture_method == "vnc":
            if not LVGL_AVAILABLE:
                return jsonify({"error": "LVGL Inspector not available for vnc capture."}), 500
            try:
                img = ScreenshotBackend.capture_vnc(vnc_host, vnc_port)
                return jsonify({"screenshot": _ndarray_to_b64(img)})
            except Exception as vnc_err:
                logger.warning(f"VNC capture failed: {vnc_err}")
                try:
                    img = ScreenshotBackend.capture_qemu_monitor(host=qemu_monitor_host, port=qemu_monitor_port)
                    return jsonify({"screenshot": _ndarray_to_b64(img), "fallback": "qemu_monitor"})
                except Exception as mon_err:
                    logger.warning(f"Monitor fallback failed: {mon_err}")
                    try:
                        img = ScreenshotBackend.capture_qemu_qmp(socket_path=qemu_qmp_socket)
                        return jsonify({"screenshot": _ndarray_to_b64(img), "fallback": "qemu_qmp"})
                    except Exception as qmp_err:
                        logger.warning(f"QMP fallback failed: {qmp_err}")
                        try:
                            if os.name == "nt":
                                b64 = capture_window_by_title_base64(qemu_titles)
                            else:
                                b64 = capture_linux_window_by_title_base64(qemu_titles)
                            return jsonify({"screenshot": b64, "fallback": "qemu_window_only"})
                        except Exception as win_err:
                            return jsonify({
                                "error": (
                                    f"VNC: {vnc_err}. Monitor: {mon_err}. "
                                    f"QMP: {qmp_err}. Window: {win_err}."
                                )
                            }), 500

        return jsonify({"error": f"Unknown capture method: {capture_method}"}), 400

    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/qemu/monitor/screenshot", methods=["GET", "POST"])
def qemu_monitor_screenshot():
    try:
        data = request.get_json(silent=True) or {}
        b64 = capture_qemu_monitor_screendump_base64(
            host=data.get("qemu_monitor_host", "127.0.0.1"),
            port=int(data.get("qemu_monitor_port", 55555)),
            ppm_path=data.get("qemu_screendump_path", "/tmp/screenshot.ppm"),
            output_png=_qemu_png_output_path(),
        )
        return jsonify({"screenshot": b64, "image_url": _qemu_png_url()})
    except Exception as e:
        logger.error(f"QEMU monitor screenshot error: {e}")
        return jsonify({"error": str(e)}), 500
# ─────────────────────────────────────────────
# Error handler
# ─────────────────────────────────────────────

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {e}")
    return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import threading
    threading.Timer(1, open_browser).start()
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    extra_files = [
        "routes/style.css",  # Example: Monitor changes in a CSS file
        "routes/index.html",  # Example: Monitor changes in an HTML file in the 'templates' folder
    ]

    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5050)
