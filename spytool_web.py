import base64
import io
import json
import tempfile
from time import sleep
from flask import Flask, render_template, request, jsonify
import os
import webbrowser
import re
import logging
from parse_pywinauto import Parser

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    OPENCV_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import pyautogui and handle if it fails
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PyAutoGUI not available: {str(e)}")
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

# Import LVGL inspector classes conditionally to avoid errors if dependencies aren't installed
try:
    from lvgl_inspector import LVGLInspector, ScreenshotBackend
    LVGL_AVAILABLE = True
except ImportError:
    LVGLInspector = None
    ScreenshotBackend = None
    LVGL_AVAILABLE = False
    logger.warning("LVGL inspector not available. Some features will be limited.")

app = Flask(__name__, template_folder="routes")


@app.route("/")
def index():
    try:
        windows_list = getWindows()
        # Render the template with the base64-encoded image
        return render_template("index.html", windows_list=windows_list)
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        return jsonify({"error": f"Failed to load index: {str(e)}"}), 500


def open_browser():
    # Open the default web browser with the Flask app
    webbrowser.open("http://127.0.0.1:5050/")


def getWindows():
    """Get the list with all windows elements

    Returns:
        [type]: List with all windows opened
    """
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        # Filter out empty titles and add some common system windows
        window_titles = [w.title for w in windows if w.title.strip() != "" and not w.title.startswith("Program Manager")]
        return window_titles
    except ImportError:
        logger.error("pygetwindow not available")
        # If pygetwindow isn't available, return an empty list
        return []
    except Exception as e:
        logger.error(f"Error getting windows: {str(e)}")
        return []


def printscreen(region=None):
    """Take a screenshot of the full screen or a region (left, top, width, height)"""
    if not PYAUTOGUI_AVAILABLE:
        logger.error("PyAutoGUI not available, cannot take screenshot")
        raise ImportError("PyAutoGUI is not available. Please install Pillow and pyscreeze.")

    try:
        screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()

        # Convert the image to base64
        img_buffer = io.BytesIO()
        screenshot.save(img_buffer, format="PNG")
        return base64.b64encode(img_buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error taking screenshot: {str(e)}")
        raise


def capture_window_by_title_base64(title_keywords):
    """Fallback screenshot capture from a visible local window title."""
    if not PYAUTOGUI_AVAILABLE:
        raise RuntimeError("PyAutoGUI not available for local window capture fallback.")

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


def parse_screen_position(text):
    # Define a regular expression pattern
    pattern = r"\(L(-?\d+), T(-?\d+), R(-?\d+), B(-?\d+)\)"

    # Use re.search to find the first match
    match = re.search(pattern, text)

    if match:
        # Extract values for L, T, R, and B
        left, top, right, bottom = match.groups()

        # Convert to the desired format
        return {
            "left": int(left),
            "top": int(top),
            "right": int(right),
            "bottom": int(bottom),
        }
    return None


def parse_auto_id(text):
    # Define regular expression pattern for auto_id
    auto_id_pattern = r'auto_id="([^"]+)"'

    # Use re.search to find the match
    auto_id_match = re.search(auto_id_pattern, text)

    # Extract auto_id
    auto_id = auto_id_match.group(1) if auto_id_match else None

    return auto_id


def parse_title(text):
    # Define regular expression pattern for title
    title_pattern = r'title="([^"]+)"'

    # Use re.search to find the match
    title_match = re.search(title_pattern, text)

    # Extract title
    title = title_match.group(1) if title_match else None

    return title


def parse_control_type(text):
    # Define regular expression pattern for control_type
    control_type_pattern = r'control_type="([^"]+)"'

    # Use re.search to find the match
    control_type_match = re.search(control_type_pattern, text)

    # Extract control_type
    control_type = control_type_match.group(1) if control_type_match else None

    return control_type


def find_node(data, target_idx):
    if "idx" in data and data["idx"] == target_idx:
        return data

    for parent in data.get("parents", []):
        result = find_node(parent, target_idx)
        if result:
            return result

    return None


def count_nodes_with_parent(data):
    count = 0  # 1 if "idx_parent" in data and data["idx_parent"] == target_idx_parent else 0

    for _ in data.get("parents"):
        count += 1  # count_nodes_with_parent(parent, target_idx_parent)

    return count


def update_nodes(text, node, idx, count_nodes_parent):
    _node = find_node(node, count_nodes_parent)
    try:
        node_1 = {
            "control_type": parse_control_type(text[2]),
            "title": parse_control_type(text[2]),
            "auto_id": parse_auto_id(text[2]),
            "position": parse_screen_position(text[0]),
            "idx": idx,
            "idx_parent": count_nodes_parent,
            "parents": [],
        }
    except Exception as err:
        node_1 = {
            "control_type": parse_control_type(text[1]),
            "title": parse_control_type(text[1]),
            "auto_id": parse_auto_id(text[1]),
            "position": parse_screen_position(text[0]),
            "idx": idx,
            "idx_parent": count_nodes_parent,
            "parents": [],
        }
    _node["parents"].append(node_1)

    return node


def recursive_parse(text, parent):
    for idx, row in enumerate(text):
        if "" == row.strip().replace(" ", "").replace("|", ""):
            begin = idx + 1
            for _idx, _line in enumerate(text[idx + 1 :]):
                if "" == text[idx + 1 + _idx].strip().replace(" ", "").replace("|", ""):
                    stop = idx + 1 + _idx
                    break
            rows = text[begin:stop]
            print(rows)
            update_nodes(rows, parent)


def parse_dump():
    with open("tree_structure.json", "r") as file:
        lines = file.readlines()


def find_node_by_idx(node, target_idx):
    if node["idx"] == target_idx:
        return node
    for child in node.get("children", []):
        result = find_node_by_idx(child, target_idx)
        if result:
            return result
    return None


@app.route("/element/<idx>", methods=["GET"])
def element(idx):
    try:
        temp_directory = tempfile.gettempdir()
        temp_file = os.path.join(temp_directory, "parsed_pywinauto.json")
        if not os.path.exists(temp_file):
            temp_file = os.path.join(temp_directory, "parsed_opencv.json")
        with open(temp_file, "r") as file:
            data = json.load(file)
        node = find_node_by_idx(data, int(idx))
        return jsonify(node)
    except FileNotFoundError:
        return jsonify({"error": "Parsed file not found"}), 404
    except Exception as e:
        logger.error(f"Error retrieving element: {str(e)}")
        return jsonify({"error": f"Failed to retrieve element: {str(e)}"}), 500


def detect_ui_elements_cv(image_data):
    """
    Detect UI elements in an image using OpenCV techniques
    This is a simplified implementation - a full implementation would include
    more sophisticated detection algorithms
    """
    try:
        if not OPENCV_AVAILABLE:
            raise ImportError("OpenCV is not available.")
        # Decode base64 image if needed, or accept numpy array
        if isinstance(image_data, str):
            # If image_data is base64 string
            img_bytes = base64.b64decode(image_data)
            img_np = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        else:
            img = image_data

        # Convert to grayscale for processing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Detect edges using Canny
        edges = cv2.Canny(blurred, 50, 150, apertureSize=3)

        # Alternative approach: use threshold to find shapes
        _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
        
        # Combine edges and threshold
        combined = cv2.bitwise_or(edges, thresh)

        # Find contours (potential UI elements)
        contours, hierarchy = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        elements = []
        for i, contour in enumerate(contours):
            # Filter out very small contours
            area = cv2.contourArea(contour)
            if area < 100:  # Minimum area threshold
                continue

            # Get bounding rectangle for the contour
            x, y, w, h = cv2.boundingRect(contour)

            # Calculate center point
            center_x = x + w // 2
            center_y = y + h // 2

            # Create an element representation
            element = {
                "idx": i,
                "parent_idx": None,  # We're not tracking parent-child relationships in this simple implementation
                "rect": {
                    "Left": x,
                    "Top": y,
                    "Right": x + w,
                    "Bottom": y + h
                },
                "center": {
                    "X": center_x,
                    "Y": center_y
                },
                "attributes": {
                    "title": f"UI Element {i}",
                    "auto_id": f"element_{i}",
                    "control_type": "Generic Control",  # This could be determined based on shape/type
                    "found_index": i,
                    "parent": {}
                },
                "node_id": f"cv_elem_{i:04d}",
                "children": []
            }
            elements.append(element)

        # Create a root node containing all detected elements
        root_node = {
            "idx": 0,
            "parent_idx": None,
            "rect": {
                "Left": 0,
                "Top": 0,
                "Right": img.shape[1],
                "Bottom": img.shape[0]
            },
            "center": {
                "X": img.shape[1] // 2,
                "Y": img.shape[0] // 2
            },
            "attributes": {
                "title": "Detected UI Elements",
                "auto_id": "root",
                "control_type": "Root Container",
                "found_index": 0,
                "parent": {}
            },
            "node_id": "cv_root_0000",
            "children": elements
        }

        return root_node
    except Exception as e:
        logger.error(f"Error in UI element detection: {str(e)}")
        raise


def _rect_to_window_dict(rect):
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
    }


def _encode_pil_image(image):
    img_buffer = io.BytesIO()
    image.save(img_buffer, format="PNG")
    return base64.b64encode(img_buffer.getvalue()).decode("utf-8")


def _inspect_with_pywinauto(window_title):
    from pywinauto import Desktop
    from pywinauto.application import Application

    desktop = Desktop(backend="uia")
    windows = desktop.windows()
    matches = [w for w in windows if window_title.lower() in w.window_text().lower()]
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
            width = max(int(rect.width()), 1)
            height = max(int(rect.height()), 1)
            screenshot_b64 = printscreen(
                region=(int(rect.left), int(rect.top), width, height)
            )
    if not screenshot_b64:
        raise RuntimeError("Failed to capture screenshot for selected window only.")

    window_rect = _rect_to_window_dict(target_wrapper.rectangle())
    return tree, screenshot_b64, window_rect


@app.route("/inspect/<path:window>", methods=["GET"])
def inspect(window):
    """Desktop inspection using pywinauto tree parsing and selected-window screenshot."""
    try:
        detected_tree, screenshot_b64, window_rect = _inspect_with_pywinauto(window)
        temp_directory = tempfile.gettempdir()
        temp_file = os.path.join(temp_directory, "parsed_pywinauto.json")
        with open(temp_file, "w") as f:
            json.dump(detected_tree, f)
        return jsonify(
            {
                "printscreen": screenshot_b64,
                "tree": detected_tree,
                "window_rect": window_rect,
            }
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as error:
        logger.error(f"Desktop inspection failed: {error}")
        return jsonify({"error": f"Inspection failed: {error}"}), 500


# ──────────────────────────────────────────────
# LVGL Inspector Routes
# ──────────────────────────────────────────────

@app.route("/lvgl/inspect", methods=["POST"])
def lvgl_inspect():
    """Route to perform LVGL inspection using pylvgl_selectors-based locators."""
    if not LVGL_AVAILABLE:
        return jsonify({"error": "LVGL Inspector not available. Required packages not installed."}), 500

    try:
        # Get parameters from the request
        data = request.json
        element = data.get("element", "root")
        max_depth = data.get("max_depth", None)
        ip = data.get("ip", "127.0.0.1")
        port = data.get("port", 8080)
        capture = data.get("capture", "none")
        vnc_host = data.get("vnc_host", "127.0.0.1")
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
            element=element,
            max_depth=max_depth,
            show_props=True,
            show_text=True,
            ip=ip,
            port=port,
            topic=topic,
            username=username,
            password=password,
            capture=capture,
            vnc_host=vnc_host,
            vnc_port=vnc_port,
            snapshot_path=snapshot_path,
            deep_scan=deep_scan,
            scan_hidden=scan_hidden,
            scan_extra_roots=scan_extra_roots,
        )
        return jsonify({"tree": tree_data, "output": "", "connection": {"topic": topic, "username": username}})
    except Exception as e:
        logger.error(f"Error in LVGL inspection: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/lvgl/screenshot", methods=["POST"])
def lvgl_screenshot():
    """Route to capture a screenshot using LVGL's screenshot capabilities."""
    if not LVGL_AVAILABLE:
        return jsonify({"error": "LVGL Inspector not available. Required packages not installed."}), 500

    try:
        import tempfile
        import os

        # Get capture method from request
        data = request.json
        capture_method = data.get("capture", "vnc")  # default to vnc
        vnc_host = data.get("vnc_host", "127.0.0.1")
        vnc_port = data.get("vnc_port", 5900)
        fb_device = data.get("fb_device", "/dev/fb0")
        qemu_titles = data.get("qemu_window_titles", ["qemu", "qemu-system", "qemu-system-x86_64"])

        # Create a temporary file path
        temp_path = os.path.join(tempfile.gettempdir(), "lvgl_screenshot.png")

        # Capture screenshot using the LVGL backend
        if capture_method == "vnc":
            try:
                img = ScreenshotBackend.capture_vnc(vnc_host, vnc_port)
            except Exception as vnc_error:
                logger.warning(f"VNC capture failed, trying local QEMU window fallback: {vnc_error}")
                try:
                    fallback_b64 = capture_window_by_title_base64(qemu_titles)
                    return jsonify({"screenshot": fallback_b64, "fallback": "local_qemu_window"})
                except Exception as fallback_error:
                    raise RuntimeError(
                        f"{vnc_error} Also failed local QEMU window fallback: {fallback_error}"
                    ) from fallback_error
        elif capture_method == "x11":
            img = ScreenshotBackend.capture_x11()
        elif capture_method == "none":
            return jsonify({"screenshot": ""})
        else:
            img = ScreenshotBackend.capture_framebuffer(fb_device)

        # Save to temp file
        ScreenshotBackend.save_annotated(img, temp_path)

        # Read and encode the image
        with open(temp_path, "rb") as img_file:
            encoded_img = base64.b64encode(img_file.read()).decode("utf-8")

        return jsonify({"screenshot": encoded_img})
    except Exception as e:
        logger.error(f"Error in LVGL screenshot: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Error handler to ensure all errors return JSON
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {str(e)}")
    # Return JSON error for all unhandled exceptions
    return jsonify({"error": f"An error occurred: {str(e)}"}), 500


if __name__ == "__main__":
    # Open the browser in a separate thread
    import threading

    threading.Timer(1, open_browser).start()
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    extra_files = [
        "routes/style.css",  # Example: Monitor changes in a CSS file
        "routes/index.html",  # Example: Monitor changes in an HTML file in the 'templates' folder
    ]

    # Run the Flask app
    app.run(debug=True, port=5050)
