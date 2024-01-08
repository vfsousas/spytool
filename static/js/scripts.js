// Dictionary to store references to tree nodes by id
var nodeDictionary = {};

function inspect() {
    var selectedValue = document.getElementById("exampleDataList").value;
    // Show loading indicator
    var loadingIndicator = document.getElementById("loadingIndicator");
    loadingIndicator.style.display = 'block';

    // Use fetch to trigger the Flask route
    fetch(`/inspect/${selectedValue}`)
        .then(response => response.json())
        .then(data => {
            displayTree(data.tree);
            // Update the HTML with the returned data
            var imgElement = document.getElementById("screenshot");
            imgElement.src = `data:image/png;base64, ${data.printscreen}`;
            var container = document.getElementById('container');
            container.style.display = 'block';
            localStorage.setItem('inspect', JSON.stringify(data.tree));

        })
        .catch(error => {
            console.error('Error:', error);
        }).finally(() => {
            // Hide loading indicator regardless of success or error
            loadingIndicator.style.display = 'none';
        });
}

function displayTree(tree) {
    var treeMenu = document.getElementById('tree-menu');
    treeMenu.innerHTML = '<h3>Tree Menu</h3>';
    var treeList = document.createElement('ul');
    createTreeMenu(tree, treeList);
    treeMenu.appendChild(treeList);
}

function createTreeMenu(node, parentElement) {
    var listItem = document.createElement('li');
    var itemText = document.createElement('span');
    itemText.textContent = node.attributes.title || 'Unnamed Node';


    var imageElement = document.createElement('img');
    if (node.attributes.control_type == 'Button') {
        // Add image based on node type
        var imageSrc = 'static/img/button.png';
        imageElement.src = imageSrc;
    }

    imageElement.style.width = '16px';  // Adjust the width as needed
    imageElement.style.marginRight = '5px';
    listItem.classList.add('list-group-item');
    listItem.classList.add('list-group-item-action');
    // Set the id of the list item
    listItem.id = node.idx;

    // Add click event to toggle visibility of children
    itemText.addEventListener('click', function () {
        toggleVisibility(listItem);
        setFocus(listItem);
    });

    listItem.appendChild(imageElement);
    listItem.appendChild(itemText);
    parentElement.appendChild(listItem);

    // Store a reference to the list item in the dictionary
    nodeDictionary[node.idx] = listItem;


    if (node.children && node.children.length > 0) {
        var sublist = document.createElement('ul');
        //sublist.style.display = 'none'; // Initially hide the children
        node.children.forEach(child => createTreeMenu(child, sublist));
        listItem.appendChild(sublist);
    }
}


// Example of how to select a node by its id
function selectNodeById(nodeId) {
    var selectedNode = nodeDictionary[nodeId];
    if (selectedNode) {
        selectedNode.focus();

        // Do something with the selected node
        console.log('Selected Node:', selectedNode);
    } else {
        console.error('Node with id', nodeId, 'not found.');
    }
}

function toggleVisibility(element) {
    var sublist = element.querySelector('ul');
    if (sublist) {
        sublist.style.display = sublist.style.display === 'none' ? 'block' : 'none';
    }
}

// Function to find a node by idx in a tree structure
function findNodeByIdx(node, targetIdx) {
    if (node.idx === targetIdx) {
        return node;
    }
    for (const child of node.children || []) {
        const result = findNodeByIdx(child, targetIdx);
        if (result) {
            return result;
        }
    }
    return null;
}

// Function to get data from localStorage and find a node by idx
function getNodeByIdxFromLocalStorage(idx) {
    const storedData = localStorage.getItem('inspect');
    const data = storedData ? JSON.parse(storedData) : null;

    if (data) {
        return findNodeByIdx(data, parseInt(idx));
    }
    return null;
}

function highlightDiv(node) {
    // Check if the div already exists
    var highlightDiv = document.getElementById('highlightDiv');
    if (!highlightDiv) {
        // Create the highlighting div
        highlightDiv = document.createElement('div');
        highlightDiv.id = 'highlightDiv';
        highlightDiv.style.position = 'fixed';
        highlightDiv.style.backgroundColor = 'rgba(0, 0, 255, 0.9)';
        document.getElementById('img_content').appendChild(highlightDiv);
    }

    const _div = document.getElementById('img_content');
    const _rect = _div.getBoundingClientRect();
    const top = _rect.top;

    // Set the position and size of the highlighting div based on rect
    highlightDiv.style.left = node.rect.Left + 'px';
    highlightDiv.style.top = (node.rect.Top + top) + 'px';
    highlightDiv.style.width = (node.rect.Right - node.rect.Left) + 'px';
    highlightDiv.style.height = (node.rect.Bottom - node.rect.Top) + 'px';
    document.getElementById('form_title').value = node.attributes.title
    document.getElementById('form_auto_id').value = node.attributes.auto_id
    document.getElementById('form_control_type').value = node.attributes.control_type
    document.getElementById('form_path').value = JSON.stringify(node.attributes)
}

document.addEventListener('mouseover', function (event) {
    // Check if the mouseover event is on a tree node
    if (event.target.tagName === 'SPAN' && event.target.parentElement.tagName === 'LI') {
        var nodeId = event.target.parentElement.id;
        // Use fetch to trigger the Flask route
        // Find the node by idx in the localStorage data
        const node = getNodeByIdxFromLocalStorage(nodeId);
        console.log(node)
        highlightDiv(node)
        // Optional: Remove the div after a certain delay (e.g., 2 seconds)
        setTimeout(function () {
            document.getElementById('img_content').removeChild(highlightDiv);
        }, 2000);
    }
});


document.addEventListener('mouseout', function (event) {
    // Check if the mouseover event is on a tree node
    if (event.target.tagName === 'SPAN' && event.target.parentElement.tagName === 'LI') {
        var element = event.target;
    }
});

// Hide the div with id "highlightDiv" when the page loads
window.onload = function () {
    //document.body.style.zoom = "80%";
    var container = document.getElementById('container');
    container.style.display = 'none';
    //document.body.style.zoom = "100%";
    //document.body.style.zoom = "80%";

};

function releaseInspectButton() {
    var button = document.getElementById('btn_inspect');
    button.disabled = false;
}

function copyPath() {
    // Create a temporary textarea element
    var textarea = document.createElement("textarea");
    var selectedValue = document.getElementById("form_path").value;

    // Set the value of the textarea to the hidden input's value
    textarea.value = selectedValue.value;

    // Append the textarea to the document
    document.body.appendChild(textarea);

    // Select the text inside the textarea
    textarea.select();

    try {
        // Use the Clipboard API to write the selected text to the clipboard
        navigator.clipboard.writeText(selectedValue).then(function () {
            console.log('Text successfully copied to clipboard:', selectedValue);
        }).catch(function (err) {
            console.error('Unable to copy text to clipboard.', err);
        });
    } catch (err) {
        // Fallback for browsers that do not support the Clipboard API
        console.error('Clipboard API not supported. Falling back to execCommand method.');
        document.execCommand('copy');
    } finally {
        // Remove the temporary textarea
        document.body.removeChild(textarea);
    }
    // Remove the temporary textarea
    document.body.removeChild(textarea);

}


document.getElementById('img_content').addEventListener('mousemove', function (event) {
    var mouseX = event.clientX; // X-coordinate relative to the viewport
    var mouseY = event.clientY; // Y-coordinate relative to the viewport

    // Optionally, you can also get the coordinates relative to the div
    var rect = event.target.getBoundingClientRect();
    var mouseXRelative = event.clientX - rect.left;
    var mouseYRelative = event.clientY - rect.top;

    // Call the function with your tree structure and coordinates
    const storedData = localStorage.getItem('inspect');
    const data = storedData ? JSON.parse(storedData) : null;

    if (data) {
        node = findNodeByCoordinates(data, mouseXRelative, mouseYRelative) //findNodeByIdx(data, parseInt(idx));
        // Event listener for keydown
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Control') {
                // Set the flag when the Ctrl key is pressed
                console.log('Ctrl key is pressed', node);
                highlightDiv(node)
                selectNodeById(node.idx);

            }
        });

    }
    return null;

});


// Function to find a node by coordinates in a tree structure
function findNodeByCoordinates(node, targetX, targetY) {
    let closestNode = null;
    let minDistance = Number.MAX_SAFE_INTEGER;

    function findClosestNode(currentNode, x, y) {
        const distance = Math.sqrt(Math.pow(x - currentNode.center.X, 2) + Math.pow(y - currentNode.center.Y, 2));
        if (distance < minDistance) {
            minDistance = distance;
            closestNode = currentNode;
        }

        for (const child of currentNode.children || []) {
            findClosestNode(child, x, y);
        }
    }

    findClosestNode(node, targetX, targetY);
    return closestNode;
}
