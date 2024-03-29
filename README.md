# Spy Tool for pywinauto

## Review

Due to the lack of good analyzers for screen elements for windows applications, this project brings a new approach so that new features and development are customized in order to create good screen analyzers

---

## The structure

This projects was build using pywinauto to get all windows elements, for the UI is used the lib PySimpleGUI and PyGame (used only to create a rectangle in the screen)

<img  src="media/UI.png"  width=402  height=425>

## See the tool execution in animation below

<img  src="media/example.gif" width=800  height=500>

*Thanks to [PySimpleGUI](https://github.com/PySimpleGUI) for the gif animation.*

---

## Features

---
### Version 1.3
- Enhancements
    - Add FULL PATH button:
        - Now is possible to copy all path since the root of object
         (inpect your window, select a node in a tree, click in FULL PATH button open the notepad/code and past the results)

### Version 1.2
- Enhancements
    - Add LIVE button:
        - Now is possible to find any object without inspect all window
         (Click in live button, put the mouse over object, wait 5 seconds)

### Version 1.1
- Fix 
    - Resize Window
    - Tree element column size
    - button copy
        - Now is possible to copy the locators to clipboard

- Enhancements
    - Display info about:
        - Application name
        - Total of elements
        - Total time to locate all elements
    - Write texts inside pywinauto elements



### Version 1.0

- Visual Inspection
- Elements organized in the tree
- Locators to be used in pywinauto generated
- Live actions like blink, click, focus and target
- Works with windows applications and web pages
