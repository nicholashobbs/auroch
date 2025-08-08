# ~/auroch/host_ui.py
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import sys
import random
import json
import time

from widgets.screenshot_viewer import ScreenshotViewer

class HostUI:
    def __init__(self):
        # Window
        self.window = Gtk.Window(title="AUROCH Host UI")
        self.window.set_default_size(1280, 800)
        self.window.connect("destroy", Gtk.main_quit)

        # Root container
        self.main_grid = Gtk.Grid(margin=10, row_spacing=10, column_spacing=10)
        self.window.add(self.main_grid)

        # Screenshot viewer (top)
        self.screenshot_viewer = ScreenshotViewer()
        self.screenshot_viewer.selection_callback = self.on_box_finalized
        self.screenshot_viewer.set_vexpand(True)
        self.screenshot_viewer.set_hexpand(True)
        self.screenshot_viewer.connect("box-drawn", self.on_box_drawn)

        # Left: selection list
        self.selection_list = Gtk.ListBox()
        self.selection_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.selection_list.connect("row-selected", self.on_selection_clicked)

        # Wrap in scroll window
        self.selection_scroll = Gtk.ScrolledWindow()
        self.selection_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.selection_scroll.set_min_content_height(150)
        self.selection_scroll.add(self.selection_list)

        # State
        self.current_box_index = None  # actual index in screenshot_viewer.boxes
        self.action_queue = []         # list of action dicts

        # Bottom area layout: left fixed, middle expandable, right fixed
        self.bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.bottom_box.set_hexpand(True)

        # Left: selection list fixed width
        self.selection_scroll.set_size_request(220, -1)
        self.bottom_box.pack_start(self.selection_scroll, False, False, 0)

        # Middle: Action Builder
        self.action_builder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.action_builder_box.set_hexpand(True)

        # Action options (use RadioButtons for exclusive selection)
        self.action_label = Gtk.Label(label="Action:")
        self.action_options_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Use RadioButton group to keep them exclusive automatically
        self.rb_click = Gtk.RadioButton.new_with_label_from_widget(None, "CLICK")
        self.rb_type = Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "TYPE")
        self.rb_scroll = Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "SCROLL")
        self.rb_move = Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "MOVE")
        # pack them
        for rb in (self.rb_click, self.rb_type, self.rb_scroll, self.rb_move):
            rb.connect("toggled", self.on_action_radio_toggled)
            self.action_options_box.pack_start(rb, False, False, 0)

        # Param area that will change with action
        self.param_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        # CLICK params: mouse button dropdown
        self.click_button_store = Gtk.ListStore(str)
        for name in ("Left", "Right", "Middle"):
            self.click_button_store.append([name])
        self.click_combo = Gtk.ComboBox.new_with_model(self.click_button_store)
        renderer_text = Gtk.CellRendererText()
        self.click_combo.pack_start(renderer_text, True)
        self.click_combo.add_attribute(renderer_text, "text", 0)
        self.click_combo.set_active(0)

        # TYPE params: entry
        self.type_entry = Gtk.Entry()
        self.type_entry.set_placeholder_text("Text to type")

        # SCROLL params: numeric entry with hint
        self.scroll_entry = Gtk.Entry()
        self.scroll_entry.set_placeholder_text("Scroll amount (e.g. -1 => ~down 100px)")

        # MOVE has no extra params for now (it's to a box region)
        # Initially, pack click controls (default)
        self.param_box.pack_start(Gtk.Label(label="Button:"), False, False, 0)
        self.param_box.pack_start(self.click_combo, False, False, 0)

        # Buttons row
        self.buttons_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_btn = Gtk.Button(label=">>> Add to Queue >>>")
        self.add_btn.connect("clicked", self.on_add_to_queue)
        self.remove_btn = Gtk.Button(label="Remove from Queue")
        self.remove_btn.connect("clicked", self.on_remove_from_queue)
        self.export_btn = Gtk.Button(label="Export JSON")
        self.export_btn.connect("clicked", self.on_export_json)
        self.buttons_row.pack_start(self.add_btn, False, False, 0)
        self.buttons_row.pack_start(self.remove_btn, False, False, 0)
        self.buttons_row.pack_end(self.export_btn, False, False, 0)

        # Assemble middle
        self.action_builder_box.pack_start(self.action_label, False, False, 0)
        self.action_builder_box.pack_start(self.action_options_box, False, False, 0)
        self.action_builder_box.pack_start(self.param_box, False, False, 0)
        self.action_builder_box.pack_start(self.buttons_row, False, False, 0)

        self.bottom_box.pack_start(self.action_builder_box, True, True, 0)

        # Right: Action Queue
        self.action_queue_list = Gtk.ListBox()
        self.action_queue_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.action_queue_list.connect("row-selected", self.on_queue_row_selected)
        self.action_queue_scroll = Gtk.ScrolledWindow()
        self.action_queue_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.action_queue_scroll.add(self.action_queue_list)
        self.action_queue_scroll.set_size_request(250, -1)
        self.bottom_box.pack_start(self.action_queue_scroll, False, False, 0)

        # Main vbox: top viewer, bottom controls
        self.main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_vbox.pack_start(self.screenshot_viewer, True, True, 0)
        self.main_vbox.pack_start(self.bottom_box, False, False, 0)
        self.main_vbox.set_hexpand(True)
        self.main_vbox.set_vexpand(True)

        self.main_grid.attach(self.main_vbox, 0, 0, 1, 1)

    # Debug hook
    def on_box_drawn(self, widget, rect_dict):
        print(f"[DEBUG] Box drawn: {rect_dict}")

    # Called by viewer when a box is finalized
    def on_box_finalized(self, rect_dict, index):
        # rect_dict already has id (index)
        label_text = f"id={rect_dict['id']} x={rect_dict['x']} y={rect_dict['y']} w={rect_dict['width']} h={rect_dict['height']}"
        print(f"[DEBUG] Adding label: {label_text}")

        row = Gtk.ListBoxRow()
        label = Gtk.Label(label=label_text, xalign=0)
        label.set_margin_top(2)
        label.set_margin_bottom(2)
        row.add(label)
        # newest on top
        self.selection_list.insert(row, 0)
        self.selection_list.show_all()

        # auto-select it
        self.current_box_index = rect_dict['id']

    # Map selection list click to actual box index (we store boxes in viewer with ids == index)
    def on_selection_clicked(self, listbox, row):
        if not row:
            self.current_box_index = None
            return
        visual_index = list(self.selection_list.get_children()).index(row)
        # newest-first mapping -> compute actual id
        actual_index = len(self.screenshot_viewer.boxes) - 1 - visual_index
        self.current_box_index = actual_index
        print(f"[DEBUG] Selected visual={visual_index} -> actual={actual_index}")
        self.screenshot_viewer.select_box(actual_index)

    # When user toggles which action is selected, swap parameter UI
    def on_action_radio_toggled(self, rb):
        if not rb.get_active():
            return
        # Clear param_box children
        for child in self.param_box.get_children():
            self.param_box.remove(child)
        # Add action-specific params
        label_widget = None
        if rb is self.rb_click:
            label_widget = Gtk.Label(label="Button:")
            self.param_box.pack_start(label_widget, False, False, 0)
            self.param_box.pack_start(self.click_combo, False, False, 0)
        elif rb is self.rb_type:
            label_widget = Gtk.Label(label="Text:")
            self.param_box.pack_start(label_widget, False, False, 0)
            self.param_box.pack_start(self.type_entry, True, True, 0)
        elif rb is self.rb_scroll:
            label_widget = Gtk.Label(label="Amount:")
            self.param_box.pack_start(label_widget, False, False, 0)
            self.param_box.pack_start(self.scroll_entry, False, False, 0)
        elif rb is self.rb_move:
            # no params for move
            label_widget = Gtk.Label(label="Move to box region")
            self.param_box.pack_start(label_widget, False, False, 0)
        self.param_box.show_all()

    def _get_selected_action_type(self):
        if self.rb_click.get_active(): return "CLICK"
        if self.rb_type.get_active(): return "TYPE"
        if self.rb_scroll.get_active(): return "SCROLL"
        if self.rb_move.get_active(): return "MOVE"
        return "CLICK"

    # Add action to queue (associate with current_box_index)
    def on_add_to_queue(self, btn):
        if self.current_box_index is None:
            print("[WARN] No bounding box selected to add action for.")
            return

        action_type = self._get_selected_action_type()
        action = {
            "type": action_type,
            "box_id": self.current_box_index,
            "params": {},
            "generated": False,
            "timestamp": time.time()
        }

        # gather params per type
        if action_type == "CLICK":
            active = self.click_combo.get_active_iter()
            if active is not None:
                model = self.click_combo.get_model()
                button_name = model[active][0]
            else:
                button_name = "Left"
            action["params"]["button"] = button_name
        elif action_type == "TYPE":
            action["params"]["text"] = self.type_entry.get_text()
        elif action_type == "SCROLL":
            # allow numeric or textual value; caller can interpret
            action["params"]["amount"] = self.scroll_entry.get_text()
        elif action_type == "MOVE":
            # no params for move; destination is the box region itself
            pass

        # Insert inferred MOVE if previous action was CLICK on different box and current is CLICK
        if self.action_queue:
            last = self.action_queue[-1]
            if last["type"] == "CLICK" and action["type"] == "CLICK" and last["box_id"] != action["box_id"]:
                move_action = self._infer_move_action(last["box_id"], action["box_id"])
                print(f"[DEBUG] Inserting inferred MOVE: {move_action}")
                self.action_queue.append(move_action)

        self.action_queue.append(action)
        self._update_action_queue_ui()

    def on_remove_from_queue(self, btn):
        sel_row = self.action_queue_list.get_selected_row()
        if not sel_row:
            print("[WARN] No queue selection to remove.")
            return
        idx = list(self.action_queue_list.get_children()).index(sel_row)
        removed = self.action_queue.pop(idx)
        print(f"[DEBUG] Removed action: {removed}")
        self._update_action_queue_ui()

    def on_queue_row_selected(self, listbox, row):
        if not row:
            return
        idx = list(self.action_queue_list.get_children()).index(row)
        act = self.action_queue[idx]
        # highlight associated box if possible
        box_id = act.get("box_id")
        if box_id is not None:
            # ensure index valid
            if 0 <= box_id < len(self.screenshot_viewer.boxes):
                self.screenshot_viewer.select_box(box_id)
        print(f"[DEBUG] Queue row selected idx={idx}: {act}")

    def _update_action_queue_ui(self):
        # clear the listbox
        for child in self.action_queue_list.get_children():
            self.action_queue_list.remove(child)

        for i, act in enumerate(self.action_queue):
            row = Gtk.ListBoxRow()
            # Build readable label text
            desc = f"[{i}] {act['type']} on box {act.get('box_id', '?')}"
            if act['type'] == "CLICK":
                desc += f" ({act['params'].get('button','Left')})"
            elif act['type'] == "TYPE":
                short = (act['params'].get('text','') or '')[:40]
                desc += f' ("{short}")'
            elif act['type'] == "SCROLL":
                desc += f" (amt={act['params'].get('amount','')})"
            elif act['type'] == "MOVE":
                # show to/from centers if present
                if "from" in act and "to" in act:
                    desc += f" from {act['from']} -> {act['to']} (d={act.get('duration_ms')})"
            if act.get("generated"):
                desc = "(auto) " + desc

            label = Gtk.Label(label=desc, xalign=0)
            label.set_margin_top(2)
            label.set_margin_bottom(2)
            if act.get("generated"):
                label.set_opacity(0.65)
            row.add(label)
            self.action_queue_list.add(row)

        self.action_queue_list.show_all()

    # infer move action (same logic as before, reproducible seed + lognormal)
    def _infer_move_action(self, from_box_id, to_box_id):
        box_from = self.screenshot_viewer.boxes[from_box_id]
        box_to = self.screenshot_viewer.boxes[to_box_id]
        from_center = [box_from["x"] + box_from["width"] // 2, box_from["y"] + box_from["height"] // 2]
        to_center = [box_to["x"] + box_to["width"] // 2, box_to["y"] + box_to["height"] // 2]
        seed = random.getrandbits(32)
        rnd = random.Random(seed)
        mu, sigma = 0.0, 0.6
        scale_ms = 400
        duration_ms = int(rnd.lognormvariate(mu, sigma) * scale_ms)
        move_action = {
            "type": "MOVE",
            "from": from_center,
            "to": to_center,
            "duration_ms": duration_ms,
            "curve": "lognormal",
            "seed": seed,
            "generated": True,
            "timestamp": time.time(),
            # we don't set box_id because MOVE is between centers; we keep both for info
            "box_id": to_box_id
        }
        return move_action

    def on_export_json(self, btn):
        out = {
            "boxes": list(self.screenshot_viewer.boxes),
            "actions": list(self.action_queue)
        }
        j = json.dumps(out, indent=2)
        print("[DEBUG] Export JSON:\n", j)
        with open("auroch_actions_export.json", "w") as f:
            f.write(j)
        print("[INFO] Exported auroch_actions_export.json")

    # run
    def run(self):
        self.screenshot_viewer.load_image("gui/recv_screen.png")
        self.window.show_all()
        Gtk.main()

if __name__ == "__main__":
    app = HostUI()
    app.run()
