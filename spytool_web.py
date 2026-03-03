import base64
import io
import json
import tempfile
from time import sleep
from flask import Flask, render_template, request
import pyautogui
import os
import webbrowser
import cv2
import numpy as np
import re
import sys
from io import StringIO

# Import LVGL inspector classes conditionally to avoid errors if dependencies aren't installed
try:
    from lvgl_inspector import LVGLInspector, ScreenshotBackend
    LVGL_AVAILABLE = True
except ImportError:
    LVGLInspector = None
    ScreenshotBackend = None
    LVGL_AVAILABLE = False
    print("Warning: LVGL inspector not available. Some features will be limited.")

app = Flask(__name__, template_folder="routes")


@app.route("/")
def index():
    windows_list = getWindows()
    # Render the template with the base64-encoded image
    return render_template("index.html", windows_list=windows_list)


def open_browser():
    # Open the default web browser with the Flask app
    webbrowser.open("http://127.0.0.1:5050/")


def getWindows():
    """Get the list with all windows elements

    Returns:
        [type]: List with all windows opened
    """
    # Using OpenCV to get window information instead of pywinauto
    # For now, return a placeholder list - in a real implementation
    # this would interface with the OS to get actual window titles
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        window_titles = [w.title for w in windows if w.title.strip() != ""]
        return window_titles
    except ImportError:
        # If pygetwindow isn't available, return an empty list
        return []


def printscreen(region=None):
    # Take a screenshot of the full screen or a region (left, top, width, height)
    screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()

    # Convert the image to base64
    img_buffer = io.BytesIO()
    screenshot.save(img_buffer, format="PNG")
    return base64.b64encode(img_buffer.getvalue()).decode("utf-8")


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
    temp_directory = tempfile.gettempdir()
    temp_file = os.path.join(temp_directory, "parsed_opencv.json")  # Changed from parsed_pywinauto.json
    with open(temp_file, "r") as file:
        data = json.load(file)
    node = find_node_by_idx(data, int(idx))
    return node


def detect_ui_elements_cv(image_data):
    """
    Detect UI elements in an image using OpenCV techniques
    This is a simplified implementation - a full implementation would include
    more sophisticated detection algorithms
    """
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

    # Detect edges using Canny
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Find contours (potential UI elements)
    contours, hierarchy = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

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


@app.route("/inspect/<path:window>", methods=["GET"])
def inspect(window):
    """Modified to use OpenCV for UI element detection instead of pywinauto"""
    try:
        import pygetwindow as gw
        
        # Get the target window
        matching_windows = [w for w in gw.getAllWindows() if window in w.title]
        if not matching_windows:
            return {"error": "Window not found"}, 404
        
        target_window = matching_windows[0]
        target_window.activate()
        
        # Get window position and size
        left, top, width, height = target_window.left, target_window.top, target_window.width, target_window.height
        
        # Take a screenshot of the window
        _printscreen = printscreen(region=(left, top, width, height))
        
        # Convert base64 screenshot to OpenCV format for processing
        img_bytes = base64.b64decode(_printscreen)
        img_np = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        
        # Use OpenCV to detect UI elements
        detected_tree = detect_ui_elements_cv(img)
        
        # Store the processed tree in a temporary file
        temp_directory = tempfile.gettempdir()
        temp_file = os.path.join(temp_directory, "parsed_opencv.json")
        with open(temp_file, "w") as f:
            json.dump(detected_tree, f)
        
        ret = {
            "printscreen": _printscreen,
            "tree": detected_tree,
            "window_rect": {"left": left, "top": top, "right": left + width, "bottom": top + height},
        }
        return ret
    except ImportError:
        # If pygetwindow isn't available, return an error
        return {"error": "Required package not available for window detection"}, 500
    except Exception as e:
        return {"error": str(e)}, 500


# ──────────────────────────────────────────────
# LVGL Inspector Routes
# ──────────────────────────────────────────────

@app.route("/lvgl/inspect", methods=["POST"])
def lvgl_inspect():
    """Route to perform LVGL inspection and return the application tree."""
    if not LVGL_AVAILABLE:
        return {"error": "LVGL Inspector not available. Required packages not installed."}, 500
    
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
        deep_scan = data.get("deep_scan", True)
        scan_hidden = data.get("scan_hidden", True)
        scan_extra_roots = data.get("scan_extra_roots", True)
        
        # Capture original stdout to catch printed output from LVGL inspector
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            # Create an instance of the LVGL inspector
            inspector = LVGLInspector()
            # Call the method that prints the tree
            tree_data = inspector.lvgl_application_structure(
                element=element,
                max_depth=max_depth,
                show_props=True,
                show_text=True,
                ip=ip,
                port=port,
                capture=capture,
                vnc_host=vnc_host,
                vnc_port=vnc_port,
                snapshot_path=snapshot_path,
                deep_scan=deep_scan,
                scan_hidden=scan_hidden,
                scan_extra_roots=scan_extra_roots
            )
        finally:
            # Restore original stdout
            sys.stdout = old_stdout
            
        # Get the printed output
        output_str = captured_output.getvalue()
        
        # For now, return a placeholder tree structure since we'd need to modify the 
        # LVGL inspector to return structured data instead of just printing
        # In a real implementation, the LVGL inspector would need to be modified to return
        # the tree structure instead of just printing it
        placeholder_tree = {
            "idx": 0,
            "parent_idx": None,
            "rect": {"Left": 0, "Top": 0, "Right": 800, "Bottom": 480},
            "center": {"X": 400, "Y": 240},
            "attributes": {
                "title": "LVGL Root Screen",
                "auto_id": "",
                "control_type": "LVGL Screen",
                "found_index": 0,
                "parent": {}
            },
            "node_id": "lvgl_root_001",
            "children": [
                {
                    "idx": 1,
                    "parent_idx": 0,
                    "rect": {"Left": 50, "Top": 50, "Right": 200, "Bottom": 100},
                    "center": {"X": 125, "Y": 75},
                    "attributes": {
                        "title": "Main Button",
                        "auto_id": "",
                        "control_type": "LVGL Button",
                        "found_index": 0,
                        "parent": {"title": "LVGL Root Screen"}
                    },
                    "node_id": "lvgl_btn_001",
                    "children": []
                },
                {
                    "idx": 2,
                    "parent_idx": 0,
                    "rect": {"Left": 200, "Top": 150, "Right": 600, "Bottom": 200},
                    "center": {"X": 400, "Y": 175},
                    "attributes": {
                        "title": "Label Widget",
                        "auto_id": "",
                        "control_type": "LVGL Label",
                        "found_index": 0,
                        "parent": {"title": "LVGL Root Screen"}
                    },
                    "node_id": "lvgl_lbl_001",
                    "children": []
                }
            ]
        }
        
        return {"tree": placeholder_tree, "output": output_str}
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/lvgl/screenshot", methods=["POST"])
def lvgl_screenshot():
    """Route to capture a screenshot using LVGL's screenshot capabilities."""
    if not LVGL_AVAILABLE:
        return {"error": "LVGL Inspector not available. Required packages not installed."}, 500
    
    try:
        import tempfile
        import os
        
        # Get capture method from request
        data = request.json
        capture_method = data.get("capture", "vnc")  # default to vnc
        vnc_host = data.get("vnc_host", "127.0.0.1")
        vnc_port = data.get("vnc_port", 5900)
        fb_device = data.get("fb_device", "/dev/fb0")
        
        # Create a temporary file path
        temp_path = os.path.join(tempfile.gettempdir(), "lvgl_screenshot.png")
        
        # Capture screenshot using the LVGL backend
        if capture_method == "vnc":
            img = ScreenshotBackend.capture_vnc(vnc_host, vnc_port)
        elif capture_method == "x11":
            img = ScreenshotBackend.capture_x11()
        else:
            img = ScreenshotBackend.capture_framebuffer(fb_device)
            
        # Save to temp file
        ScreenshotBackend.save_annotated(img, temp_path)
        
        # Read and encode the image
        with open(temp_path, "rb") as img_file:
            encoded_img = base64.b64encode(img_file.read()).decode("utf-8")
            
        return {"screenshot": encoded_img}
    except Exception as e:
        return {"error": str(e)}, 500


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