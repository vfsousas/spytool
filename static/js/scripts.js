function inspect() {
    var selectedValue = document.getElementById("myDropdown").value;
    console.log(selectedValue)
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
        })
        .catch(error => {
            console.error('Error:', error);
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

    // Add icon based on node type
    var iconClass = node.children && node.children.length > 0 ? 'fa-folder' : 'fa-file';
    var iconElement = document.createElement('i');
    iconElement.classList.add('fas', iconClass);
    iconElement.style.marginRight = '5px';

    // Set the id of the list item
    listItem.id = node.idx;

    // Add click event to toggle visibility of children
    itemText.addEventListener('click', function () {
        toggleVisibility(listItem);
    });

    listItem.appendChild(iconElement);
    listItem.appendChild(itemText);
    parentElement.appendChild(listItem);

    if (node.children && node.children.length > 0) {
        var sublist = document.createElement('ul');
        //sublist.style.display = 'none'; // Initially hide the children
        node.children.forEach(child => createTreeMenu(child, sublist));
        listItem.appendChild(sublist);
    }
}


function toggleVisibility(element) {
    var sublist = element.querySelector('ul');
    if (sublist) {
        sublist.style.display = sublist.style.display === 'none' ? 'block' : 'none';
    }
}

document.addEventListener('mouseover', function (event) {
    // Check if the mouseover event is on a tree node
    if (event.target.tagName === 'SPAN' && event.target.parentElement.tagName === 'LI') {
        var nodeId = event.target.parentElement.id;
        console.log('Hovered over tree node with id:', nodeId);
        // Use fetch to trigger the Flask route
        fetch(`/element/${nodeId}`)
            .then(response => response.json())
            .then(data => {
                console.log(data);
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
                console.log('The top position of myDiv is:', top);

                // Set the position and size of the highlighting div based on rect
                highlightDiv.style.left = data.rect.Left + 'px';
                highlightDiv.style.top = (data.rect.Top + top) + 'px';
                highlightDiv.style.width = (data.rect.Right - data.rect.Left) + 'px';
                highlightDiv.style.height = (data.rect.Bottom - data.rect.Top) + 'px';



                // Optional: Remove the div after a certain delay (e.g., 2 seconds)
                setTimeout(function () {
                    document.getElementById('img_content').removeChild(highlightDiv);
                }, 2000);
            })
            .catch(error => {
                console.error('Error:', error);
            });
    }
});

// Hide the div with id "highlightDiv" when the page loads
window.onload = function () {
    var container = document.getElementById('container');
    container.style.display = 'none';
};