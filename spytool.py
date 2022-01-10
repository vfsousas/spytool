#!/usr/bin/python
# -*- coding: UTF-8 -*-
#------------------------------------------------------------------------------
# Vanderson Ferreira de Sousa
# vandersom@gmail.com
#------------------------------------------------------------------------------


from pywinauto import Desktop
import pywinauto
from pywinauto import mouse
import PySimpleGUI as sg
import ctypes
import win32api
import time

import win32gui
import pygame as pg
import sys
import win32api
import win32con
import win32gui


class AtlasSpy():
    def __init__(self) -> None:
        self.MainForm = []
        self.old_window_obj_list = {}
        self.old_window = []
        self.node_id = 0
        self.objCount = 0
        self.window_objects = []
        user32 = ctypes.windll.user32
        self.screensize = user32.GetSystemMetrics(
            0), user32.GetSystemMetrics(1)
        # self.drawRect()

    def drawRect(self, rect: dict) -> None:
        """ Draw in the screen the rectangle in the color fuschia, when the action TARGET is clicked
            To draw the rectangle is used pygame as lib and win32gui lib to set tranparent layout of the background of rectangle.

        Args:
            rect (dict): Receive the cordinates of rectangle 
        """
        pg.init()

        fuchsia = (255, 0, 128)  # Transparency color
        dark_red = (139, 0, 0)

        info = pg.display.Info()
        screen = pg.display.set_mode(
            (info.current_w, info.current_h), pg.NOFRAME)

        # Create layered window
        hwnd = pg.display.get_wm_info()["window"]
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                               win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED)
        # Set window transparency color
        win32gui.SetLayeredWindowAttributes(
            hwnd, win32api.RGB(*fuchsia), 0, win32con.LWA_COLORKEY)
        screen.fill(fuchsia)  # Transparent background
        pg.draw.rect(screen, dark_red, pg.Rect(
            rect['l'],  rect['t'],  rect['r'] - rect['l'], rect['b'] - rect['t']))
        pg.display.update()
        time.sleep(3)
        pg.quit()

    def rect(self, element: pywinauto.controls.uia_controls) -> list:
        """ 
            Receive the element and extract the rectangle coordinates  of it.

        Args:
            element (pywinauto.controls.uia_controls): The pywinauto element

        Returns:
            list: Coordinates converted to a list
        """
        rect = str(element.rectangle()).split(",")
        rect[0] = int(str(rect[0]).replace(
            "(L-", "").replace("(L", "").strip())
        rect[1] = int(str(rect[1]).replace("T-", "").replace("T", "").strip())
        rect[2] = int(str(rect[2]).replace("R-", "").replace("R", "").strip())
        rect[3] = int(str(rect[3]).replace(
            "B-", "").replace("B", "").replace(")", "").strip())
        return rect

    def locator(self, element: pywinauto.controls.uia_controls) -> dict:
        """Receive the element and extract the locators of it.

        Args:
            element (pywinauto.controls.uia_controls): The pywinauto element

        Returns:
            dict:  Locators converted to a list
        """
        localLocator = {}
        if element.element_info.automation_id != '':
            localLocator = {**localLocator,
                            'auto_id': element.element_info.automation_id}
        if element.friendly_class_name() != '':
            localLocator = {**localLocator,
                            'class_name': element.friendly_class_name()}

        if element.element_info.control_type != '':
            localLocator = {**localLocator,
                            'control_type': element.element_info.control_type}

        legacy = element.legacy_properties()
        if legacy['Description'] != '':
            localLocator = {**localLocator,
                            'Description': legacy['Description']}

        if legacy['Name'] != '':
            localLocator = {**localLocator, 'Name': legacy['Name']}

        try:
            if legacy['title'] != '':
                localLocator = {**localLocator, 'title': legacy['title']}
        except:
            pass

        return localLocator

    def elementToDict(self, element: pywinauto.controls.uia_controls, rectangle: list, locators: list) -> dict:
        """ Receive a pywinauto element and extract all possible infomation about it

        Args:
            element (pywinauto.controls.uia_controls): pywinauto screen element
            rectangle (list): List with all Rectangle coordinates
            locators (list):  List with all locators found

        Returns:
            dict: Dictionary with all information about the element
        """
        obj = {
            "id": self.node_id+1,
            "name": element.element_info.name,
            "friendly_class_name": element.friendly_class_name(),
            "is_dialog": element.is_dialog(),
            "automation_id": element.element_info.automation_id,
            "children_texts": element.children_texts(),
            "rect": {"l": rectangle[0],  "r": rectangle[2], "t": rectangle[1], "b": rectangle[3], 'center': (int((rectangle[2]+rectangle[0])/2), int((rectangle[3]+rectangle[1])/2))},
            "visible": element.is_visible(),
            "locators": locators,
            'childrensCount': element.control_count(),
            'childrens': []
        }
        return obj

    def Wrapper(self, element: pywinauto.controls.uia_controls) -> dict:
        """[summary]

        Args:
            element (pywinauto.controls.uia_controls): pywinauto screen element

        Returns:
            dict: Dictionaries with elements information and locators
        """
        elementRectangle = self.rect(element)
        locators = self.locator(element)
        elemDict = self.elementToDict(element, elementRectangle, locators)
        self.window_objects.append([element, elemDict])
        element.draw_outline()
        return elemDict, locators

    def children(self, childrenList: list, childrens: list, treedata: sg.TreeData, parent) -> dict:
        """This is a recursive function used to find elements, for each element extract the information and locators and use this generate the tree in tue UI

        Args:
            childrenList (list): List with all elements that was found in the previews round of this recursive function
            childrens (list): Current node of object found in the pywinauto UI element
            treedata (sg.TreeData): PySimpleGUI Tree element to manipulate and add elements to it.
            parent ([type]): Preview NodeID of PySimpleGUI Tree

        Returns:
            dict: Tree with all elements of UI pywinauto items
        """
        for item in reversed(childrenList):
            elem, locator = self.Wrapper(
                item)
            self.node_id += 1
            treedata.Insert(parent, self.node_id, elem['friendly_class_name'], values=[
                            item.element_info.name])
            childrens['childrens'].append(elem)
            chil = childrens['childrens'][len(childrens['childrens'])-1]
            if len(item.children()) > 0:
                self.children(item.children(), chil, treedata, self.node_id)
        return childrens

    def key_to_id(self, tree: sg.Tree, key: int):
        """For each PySimpleGUI Tree element to interact with this item, is needed to find the current Key ID

        Args:
            tree (sg.Tree): PySimpleGUI Tree
            key (int): ID of element of the tree

        Returns:
            [type]: Return the currect Tree element 
        """
        for k, v in tree.IdToKey.items():
            try:
                if v == int(key):
                    return k
            except:
                if v == key:
                    return k

    def getWindows(self):
        """ Get the list with all windows elements 

        Returns:
            [type]: List with all windows opened
        """
        desktop = Desktop(backend="uia").windows()
        windows = ([w.window_text() for w in desktop])
        windows.pop(0)
        return windows 

    def treeEvent(self, id: int, ui) -> None:
        """ When user click in the tree, the locators is uptdated in the textbox

        Args:
            id (int): [description] id of PySimpleGUI tree element
            ui ([type]): PySimpleGUI textbox element
        """
        for item in self.window_objects:
            if int(item[1]['id']) == id:
                ui.Element('textbox').Update(item[1]['locators'])
                break

    def targetEvent(self, ui, tree: sg.Tree):
        """ When the user click in the TARGET button, after 5 seconds the mouse pointer position is discovered.
        With X and Y from the mouse position, a loop thru all elements to find where elements the mouse the be over
        After discover all elements, the smallest one is selected and the rectangle of this element is displayed

        Args:
            ui ([type]): PySimpleGUI UI element
            tree (sg.Tree): PySimpleGUI Tree
        """
        for _ in range(5):
            time.sleep(1)

        rects = []
        x, y = win32api.GetCursorPos()
        for item in self.window_objects:
            if x >= item[1]['rect']['l'] and x <= item[1]['rect']['r']:
                if y >= item[1]['rect']['t'] and y <= item[1]['rect']['b']:
                    rect = {'id': item[1]['id'], 'rect': (
                        item[1]['rect']['r'] - item[1]['rect']['l']) * (item[1]['rect']['b']-item[1]['rect']['t'])}
                    rects.append(rect)
        result = sorted(rects, key=lambda i: i['rect'])
        idResult = int(result[0]['id'])
        for item in self.window_objects:
            if item[1]['id'] == idResult:
                iid = self.key_to_id(tree, idResult)
                tree.Widget.see(iid)
                tree.Widget.selection_set(iid)
                self.drawRect(item[1]['rect'])
                break
        ui.Element('TARGET').Update('TARGET')

    def displayPySimpleGUI(self):
        """ 
        This funcion creates te UI, get all windows and fill the listbox with windows Title

        The UI run in a infinite loop and inside this loop is possile to get user action in UI

        """
        windows = self.getWindows()
        treedata: sg.TreeData = sg.TreeData()
        tree = sg.Tree(treedata, key='-TREE-',  headings=[
                       '', ], auto_size_columns=True, col0_width=35, show_expanded=True,  enable_events=True)
        lay = [[
                sg.Column([
                    [sg.Text("Windows List"), sg.Combo(windows, size=(
                        25, 1),  enable_events=True, readonly=True,  key='combo'), sg.Button("INSPECT")],
                    [tree],
                    [sg.Button("BLINK"), sg.Button("FOCUS"),
                     sg.Button("CLICK"), sg.Button("TARGET")],
                    [sg.Text("Locators")],
                    [sg.Multiline(size=(39, 1), key='textbox'),
                     sg.Button("COPY")]                   
                ]
                )]]
        window = sg.Window(title="SpyTool", layout=lay,  keep_on_top=True,
                           return_keyboard_events=True, location=(self.screensize[0]-400, 0))
        while True:
            event, values = window.read()
            if event == '-TREE-':
                self.treeEvent(values['-TREE-'][0], window)

            if event == 'TARGET':
                self.targetEvent(window, tree)

            if event == 'INSPECT':
                treedata: sg.TreeData = sg.TreeData()
                desktop = Desktop(backend="uia").windows()

                windows = (
                    [w for w in desktop if values['combo'] in w.window_text()])[0]
                windows.set_focus()
                MainForm, locator = self.Wrapper(windows)
                MainForm = self.children(
                    windows.children(), MainForm, treedata, '')
                tree.update(values=treedata)

            if event == 'CLOSE' or event == sg.WIN_CLOSED:
                pg.quit()
                sys.exit()

            if event == 'BLINK':
                objId = int(values['-TREE-'][0])
                self.window_objects[objId][0].draw_outline()

            if event == 'CLICK':
                objId = int(values['-TREE-'][0])
                try:
                    self.window_objects[objId][0].click()
                except Exception as e:
                    center = self.window_objects[objId][1]['rect']['center']
                    x, y = win32api.GetCursorPos()
                    mouse.click(button='left', coords=(center[0], center[1]))
                    mouse.move(coords=(x, y))
                    pass


if __name__=="__main__":
    spy = AtlasSpy()
    spy.displayPySimpleGUI()
