import base64
import io
import json
import tempfile
from time import sleep
from flask import Flask, render_template
import pyautogui
import os
import webbrowser
from pywinauto import Desktop
import pygetwindow as gw
import re

from parse_pywinauto import Parser

app = Flask(__name__, template_folder="routes")


@app.route("/")
def index():
    windows_list = getWindows()
    # Render the template with the base64-encoded image
    return render_template("index.html", windows_list=windows_list)


def open_browser():
    # Open the default web browser with the Flask app
    webbrowser.open("http://127.0.0.1:5000/")


def getWindows():
    """Get the list with all windows elements

    Returns:
        [type]: List with all windows opened
    """
    desktop = Desktop(backend="uia").windows()
    block_list = ["Taskbar", "", "SpyTool - Web", "Program Manager"]
    windows = [w.window_text() for w in desktop if w.window_text() not in block_list]
    windows.pop(0)
    return windows


def printscreen():
    # Take a screenshot
    screenshot = pyautogui.screenshot()

    # Remove 10 pixels from the bottom of the image
    width, height = screenshot.size
    screenshot = screenshot.crop((0, 0, width, height - 60))

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
    temp_file = os.path.join(temp_directory, "parsed_pywinauto.json")
    with open(temp_file, "r") as file:
        data = json.load(file)
    node = find_node_by_idx(data, int(idx))
    return node


@app.route("/inspect/<window>", methods=["GET"])
def inspect(window):
    # Get the current active window
    current_window = gw.getActiveWindow()

    desktop = Desktop(backend="uia").windows()
    windows = ([w for w in desktop if window in w.window_text()])[0]
    title = windows.window_text()
    windows.restore()
    windows.maximize()
    windows.set_focus()
    _printscreen = printscreen()
    current_window.activate()

    temp_directory = tempfile.gettempdir()
    temp_file = os.path.join(temp_directory, "output_pywinauto.txt")
    Desktop(backend="uia").window(title=title).dump_tree(depth=None, filename=temp_file)
    parser = Parser()
    parser_tree = parser.parse(temp_file)

    ret = {"printscreen": _printscreen, "tree": parser_tree}
    return ret  # Return a response to the fetch request


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
    app.run(debug=True)
