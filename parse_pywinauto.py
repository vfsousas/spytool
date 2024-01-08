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

    def parse(self, temp_file):
        with open(temp_file, "r") as file:
            string = file.read()

            # Remove lines containing '[' and ']'
            filtered_string = re.sub(r"\[.*?\]|\].*?\[", "", string)

            pattern = r"^\s*\|{2,}\s*$"

            # Use re.sub to replace matching lines with an empty string
            filtered_string = re.sub(
                r"^.*\|\s*$", "", filtered_string, flags=re.MULTILINE
            )

            # Remove empty lines
            result_string = "\n".join(
                line for line in filtered_string.split("\n") if line.strip()
            )

            # Define a regular expression pattern to match the coordinates pattern
            pattern = re.compile(r"\(L(-?\d+),\s*T(-?\d+),\s*R(\d+),\s*B(\d+)\)")
            # updated_data = re.sub(pattern, replace_coordinates, result_string)
            pattern_1 = r"\(L(-?\d+),\s*T(-?\d+),\s*R(\d+),\s*B(\d+)\)"

            nodes_list = []
            _new_data = []
            element_count = 0
            for _data in result_string.split("\n")[1:]:
                count = _data.count("|")
                _data = _data.replace("|", "").strip()
                # Use re.search to find the pattern in the line
                match = re.search(pattern_1, _data)
                if match:
                    # Check if a match is found
                    left = int(match.group(1))
                    top = int(match.group(2))
                    right = int(match.group(3))
                    bottom = int(match.group(4))
                    if left is not None:
                        node = {
                            "Left": left,
                            "Top": top,
                            "Right": right,
                            "Bottom": bottom,
                        }
                        _new_data = [count, element_count, node]
                        element_count += 1

                # Pattern for title

                title_pattern = r'title="(.*?)"'
                # Pattern for auto_id
                auto_id_pattern = r'auto_id="(.*?)"'
                # Pattern for control_type
                control_type_pattern = r'control_type="(.*?)"'
                # Use re.search to find each pattern in the line
                title_match = re.search(title_pattern, _data)
                auto_id_match = re.search(auto_id_pattern, _data)
                control_type_match = re.search(control_type_pattern, _data)

                # Extract values if a match is found
                title = title_match.group(1) if title_match else None
                auto_id = auto_id_match.group(1) if auto_id_match else None
                control_type = (
                    control_type_match.group(1) if control_type_match else None
                )
                node = {
                    "title": title,
                    "auto_id": auto_id,
                    "control_type": control_type,
                    "found_index": 0,
                }
                if title or auto_id or control_type:
                    _new_data[2].update(node)
                    nodes_list.append(_new_data)
                    _new_data = []
            tree_root, node_dict = self.build_tree(nodes_list)
            # Convert the tree to a dictionary with parent indices, "rect" key, "center" key, "parent" key, and "node_id" key
            tree_dict_with_id = self.tree_to_dict_with_id(tree_root, node_dict)
            tmp_path_to_save = os.path.join(self.temp_folder, "parsed_pywinauto.json")
            self.save_to_json(tmp_path_to_save, tree_dict_with_id)
            return tree_dict_with_id

    def find_parent_node(self, node, idx):
        if "idx" in node:
            print(node["idx"])
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

        return {"X": center_x, "CY": center_y}

    def build_tree(self, nodes):
        node_dict = {}

        for position, idx, attributes in nodes:
            current_node = TreeNode(idx, None, attributes)
            node_dict[idx] = current_node

            if position > 0:
                parent_idx = nodes[position - 1][1]  # Parent's idx
                parent_node = node_dict[parent_idx]
                parent_node.children.append(current_node)
                current_node.parent_idx = parent_idx  # Set parent index directly

        # Find and return the root node
        root_candidates = set(node_dict.keys()) - set(p[1] for p in nodes if p[0] > 0)
        root = node_dict[next(iter(root_candidates))]
        return root, node_dict  # Return node_dict as well

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

    def tree_to_dict_with_id(self, node, node_dict):
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
            parent_node = node_dict[node.parent_idx]
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
                self.tree_to_dict_with_id(child, node_dict) for child in node.children
            ],
        }
        return node_dict

    def save_to_json(self, path, content):
        # Save the dictionary to the JSON file
        with open(path, "w") as json_file:
            json.dump(content, json_file, indent=2)
