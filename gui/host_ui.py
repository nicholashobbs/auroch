# ~/auroch/host_ui.py
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import sys

# Import our custom widget
from widgets.screenshot_viewer import ScreenshotViewer
from data_structures import Action


class HostUI:
    def __init__(self):
        self.window = Gtk.Window(title="AUROCH Host UI")
        self.window.set_default_size(1280, 800)
        self.window.connect("destroy", Gtk.main_quit)

        # Create the main layout
        self.main_grid = Gtk.Grid(margin=10, row_spacing=10, column_spacing=10)
        self.window.add(self.main_grid)

        # Create and add the screenshot viewer
        self.screenshot_viewer = ScreenshotViewer()
        self.screenshot_viewer.selection_callback = self.on_box_finalized
        self.screenshot_viewer.set_vexpand(True)
        self.screenshot_viewer.set_hexpand(True)
        self.screenshot_viewer.connect("box-drawn", self.on_box_drawn)

        self.selection_list = Gtk.ListBox()
        self.selection_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.selection_list.connect("row-selected", self.on_selection_clicked)

        # Wrap the list in a scrollable container
        self.selection_scroll = Gtk.ScrolledWindow()
        self.selection_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.selection_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.selection_scroll.set_min_content_height(150)
        self.selection_scroll.add(self.selection_list)
        self.selection_scroll.set_size_request(200, 200)  # or whatever height you want


       # Create bottom horizontal layout
        self.bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.bottom_box.set_hexpand(True)

        # Left: Selection list (fixed width)
        self.selection_scroll.set_size_request(250, -1)  # fixed width, height auto
        self.bottom_box.pack_start(self.selection_scroll, False, False, 0)

        # Middle: Action panel placeholder (expandable)
        self.middle_placeholder = Gtk.Label(label="(Apply Actions Panel Placeholder)")
        self.middle_placeholder.set_hexpand(True)
        self.middle_placeholder.set_vexpand(False)
        self.bottom_box.pack_start(self.middle_placeholder, True, True, 0)

        # Right: Action queue (fixed width)
        self.right_placeholder = Gtk.Label(label="(Action Queue Placeholder)")
        self.right_placeholder.set_size_request(250, -1)
        self.bottom_box.pack_start(self.right_placeholder, False, False, 0)



        self.main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_vbox.pack_start(self.screenshot_viewer, True, True, 0)
        self.main_vbox.pack_start(self.bottom_box, False, False, 0)

        self.main_vbox.set_hexpand(True)
        self.main_vbox.set_vexpand(True)



        self.main_grid.attach(self.main_vbox, 0, 0, 1, 1)



    def run(self):
        # Load an initial test image
        self.screenshot_viewer.load_image("gui/recv_screen.png")
        self.window.show_all()
        Gtk.main()

    def on_box_drawn(self, widget, rect_dict):
        print(f"[DEBUG] Box drawn: {rect_dict}")

    def on_box_finalized(self, rect_dict, index):
        x, y, w, h = rect_dict["x"], rect_dict["y"], rect_dict["width"], rect_dict["height"]
        label_text = f"x={x}, y={y}, w={w}, h={h}"
        print(f"[DEBUG] Adding label: {label_text}")
        row = Gtk.ListBoxRow()
        label = Gtk.Label(label=label_text, xalign=0)
        label.set_margin_top(2)
        label.set_margin_bottom(2)
        row.add(label)
        self.selection_list.insert(row, 0)  # Insert at the top
        self.selection_list.show_all()


    def on_selection_clicked(self, listbox, row):
        if row:
            visual_index = list(self.selection_list.get_children()).index(row)
            actual_index = len(self.screenshot_viewer.boxes) - 1 - visual_index
            self.screenshot_viewer.select_box(actual_index)


if __name__ == "__main__":
    app = HostUI()
    app.run()