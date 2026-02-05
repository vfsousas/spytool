import csv
import hashlib
import json
import os
import tempfile
import re


class TreeNode:
    def __init__(self, idx, parent_idx, attributes):
        self.idx = idx
        self.parent_idx = parent_idx
        self.attributes = attributes
        self.children = []


class Parser:
    def __init__(self) -> None:
        self.temp_folder = tempfile.gettempdir()

    def save_to_csv(self, data_list, file_path):
        with open(file_path, "w", newline="") as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerows(data_list)

    def remove_brackets_lines(self, input_string):
        # Split the input string into lines
        lines = input_string.split("\n")
        # Remove list-like lines that only contain identifiers
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            pipe_stripped = stripped.replace("|", "").strip()
            if pipe_stripped.startswith("[") and pipe_stripped.endswith("]"):
                continue
            filtered_lines.append(line)

        # Join the filtered lines back into a string
        result_string = "\n".join(filtered_lines)

        return result_string

    def parse(self, temp_file):
        with open(temp_file, "r") as file:
            string = file.read()

            filtered_string = self.remove_brackets_lines(string)

            result_lines = [
                line for line in filtered_string.splitlines() if line.strip()
            ]
            result_string = "\n".join(result_lines)
            # Define a regular expression pattern to match the coordinates pattern
            pattern_1 = r"\(L(-?\d+),\s*T(-?\d+),\s*R(-?\d+),\s*B(-?\d+)\)"
            title_from_line_pattern = r"-\s*'(.*?)'\s*\("

            def parse_child_window_attributes(text):
                title_pattern = r'title="(.*?)"'
                auto_id_pattern = r'auto_id="(.*?)"'
                control_type_pattern = r'control_type="(.*?)"'
                title_match = re.search(title_pattern, text)
                auto_id_match = re.search(auto_id_pattern, text)
                control_type_match = re.search(control_type_pattern, text)
                return {
                    "title": title_match.group(1) if title_match else None,
                    "auto_id": auto_id_match.group(1) if auto_id_match else None,
                    "control_type": control_type_match.group(1)
                    if control_type_match
                    else None,
                }

            def parse_title_from_rect_line(text):
                title_match = re.search(title_from_line_pattern, text)
                return title_match.group(1) if title_match else None

            nodes_list = []
            element_count = 0
            pending = None
            seen_counts = {}

            lines = result_string.splitlines()
            if lines and "Control Identifiers" in lines[0]:
                lines = lines[1:]
            for raw in lines:
                count = raw.count("|")
                _data = raw.replace("|", "").strip()

                match = re.search(pattern_1, _data)
                if match:
                    if pending:
                        nodes_list.append(pending)
                        pending = None
                    left = int(match.group(1))
                    top = int(match.group(2))
                    right = int(match.group(3))
                    bottom = int(match.group(4))
                    node = {
                        "Left": left,
                        "Top": top,
                        "Right": right,
                        "Bottom": bottom,
                        "title": parse_title_from_rect_line(_data),
                        "auto_id": None,
                        "control_type": None,
                        "found_index": 0,
                    }
                    pending = [count, element_count, node]
                    element_count += 1
                    continue

                if "child_window(" in _data and pending:
                    attrs = parse_child_window_attributes(_data)
                    pending[2].update(attrs)
                    key = (
                        pending[2].get("title"),
                        pending[2].get("auto_id"),
                        pending[2].get("control_type"),
                    )
                    seen_counts[key] = seen_counts.get(key, 0) + 1
                    pending[2]["found_index"] = seen_counts[key] - 1
                    nodes_list.append(pending)
                    pending = None

            if pending:
                nodes_list.append(pending)
            self.save_to_csv(nodes_list, "output.csv")
            tree_root, node_dict = self.build_tree(nodes_list)
            if tree_root is None:
                return {}
            # Convert the tree to a dictionary with parent indices, "rect" key, "center" key, "parent" key, and "node_id" key
            tree_dict_with_id = self.tree_to_dict_with_id(tree_root, node_dict)
            tmp_path_to_save = os.path.join(self.temp_folder, "parsed_pywinauto.json")
            self.save_to_json(tmp_path_to_save, tree_dict_with_id)

            return tree_dict_with_id

    def find_parent_node(self, node, idx):
        if "idx" in node:
            if node["idx"] == idx:
                return node
            if "parent" in node and node["parent"]:
                return self.find_parent_node(node["parent"], idx)
            return None
        if isinstance(node, list):
            for n in node:
                if n["idx"] == idx:
                    return n
                if "parent" in n and n["parent"]:
                    x = self.find_parent_node(n["parent"], idx)
                    return x
            return None  # Return None if the node is not found in the current list

    def find_parent(self, node, idx, idx_parent, nodes_list):
        latest_line = None
        for _idx, line in enumerate(nodes_list):
            if _idx == idx:
                break
            if line[0] == idx_parent - 1:
                latest_line = line[1]
        return self.find_parent_node(node, latest_line)

    def calculate_center(self, rect):
        left = rect["Left"]
        top = rect["Top"]
        right = rect["Right"]
        bottom = rect["Bottom"]

        center_x = (left + right) / 2
        center_y = (top + bottom) / 2

        return {"X": center_x, "Y": center_y}

    def build_tree(self, nodes):
        node_dict = {}
        roots = []
        stack = []

        for depth, idx, attributes in nodes:
            current_node = TreeNode(idx, None, attributes)
            node_dict[idx] = current_node

            while stack and stack[-1][0] >= depth:
                stack.pop()

            if stack:
                parent_node = stack[-1][1]
                parent_node.children.append(current_node)
                current_node.parent_idx = parent_node.idx
            else:
                roots.append(current_node)

            stack.append((depth, current_node))

        if not roots:
            return None, node_dict
        if len(roots) == 1:
            return roots[0], node_dict

        # Create a synthetic root if multiple roots are found
        rects = [
            r.attributes
            for r in roots
            if all(k in r.attributes for k in ["Left", "Top", "Right", "Bottom"])
        ]
        if rects:
            left = min(r["Left"] for r in rects)
            top = min(r["Top"] for r in rects)
            right = max(r["Right"] for r in rects)
            bottom = max(r["Bottom"] for r in rects)
        else:
            left = top = right = bottom = 0

        root_attributes = {
            "Left": left,
            "Top": top,
            "Right": right,
            "Bottom": bottom,
            "title": "Root",
            "auto_id": None,
            "control_type": "Root",
            "found_index": 0,
        }
        root = TreeNode(-1, None, root_attributes)
        root.children.extend(roots)
        for child in roots:
            child.parent_idx = root.idx
        node_dict[root.idx] = root
        return root, node_dict

    def generate_node_id(self, attributes):
        # Concatenate relevant attribute values into a string
        attribute_string = f"{attributes['title']}_{attributes['auto_id']}_{attributes['control_type']}_{attributes['found_index']}"

        # Add a fixed seed to the string
        seed = "atlas"
        combined_string = attribute_string + seed

        # Hash the string to generate a unique identifier
        node_id = hashlib.sha256(combined_string.encode()).hexdigest()
        # Take the first 8 characters for a shorter ID
        return node_id[:8]

    def tree_to_dict_with_id(self, node, node_map):
        # Include "rect" key for rectangle attributes
        rect_attributes = {
            "Left": node.attributes["Left"],
            "Top": node.attributes["Top"],
            "Right": node.attributes["Right"],
            "Bottom": node.attributes["Bottom"],
        }

        # Calculate the center and include it in the "center" key
        center_attributes = self.calculate_center(rect_attributes)

        # Include "parent" key for parent node's attributes
        parent_attributes = {}
        if node.parent_idx is not None:
            parent_node = node_map[node.parent_idx]
            parent_attributes = {
                key: value
                for key, value in parent_node.attributes.items()
                if key not in ["Left", "Top", "Right", "Bottom"]
            }

        # Generate a unique identifier for the node
        node_id = self.generate_node_id(node.attributes)

        node_dict = {
            "idx": node.idx,
            "parent_idx": node.parent_idx,
            "rect": rect_attributes,
            "center": center_attributes,
            "attributes": {
                "title": node.attributes["title"],
                "auto_id": node.attributes["auto_id"],
                "control_type": node.attributes["control_type"],
                "found_index": node.attributes["found_index"],
                "parent": parent_attributes,
            },
            "node_id": node_id,
            "children": [
                self.tree_to_dict_with_id(child, node_map) for child in node.children
            ],
        }
        return node_dict

    def save_to_json(self, path, content):
        # Save the dictionary to the JSON file
        with open(path, "w") as json_file:
            json.dump(content, json_file, indent=2)
