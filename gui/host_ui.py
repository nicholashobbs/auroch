# ~/auroch/gui/host_ui.py
from datetime import datetime
import gi
gi.require_version('Gtk', '3.0')
import sys
import random
import json
import time
import subprocess
from gi.repository import Gtk, GLib, Gdk, GdkPixbuf
from pathlib import Path
from widgets.screenshot_viewer import ScreenshotViewer

PI_PORT = 5555

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
        self.selection_scroll.set_min_content_height(220)
        self.selection_scroll.add(self.selection_list)

        # State
        self.current_box_index = None  # actual index in screenshot_viewer.boxes
        self.action_queue = []         # list of action dicts

        # Bottom area layout: left fixed, middle expandable, right fixed
        self.bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.bottom_box.set_hexpand(True)
        self.bottom_box.set_size_request(-1, 260)  # make bottom section taller


        # Left column: selection list only (wider)
        self.selection_scroll.set_size_request(320, -1)  # wider ~25%
        self.left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.left_col.set_size_request(320, -1)
        self.left_col.pack_start(self.selection_scroll, True, True, 0)
        self.bottom_box.pack_start(self.left_col, False, False, 0)

        # Middle: Action Builder
        self.action_builder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.action_builder_box.set_hexpand(True)
        self.action_builder_box.set_vexpand(False)

        # Action options (use RadioButtons for exclusive selection)
        self.action_options_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Use RadioButton group to keep them exclusive automatically
        self.rb_click = Gtk.RadioButton.new_with_label_from_widget(None, "CLICK")
        self.rb_type  = Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "TYPE")
        self.rb_scroll= Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "SCROLL")
        self.rb_move  = Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "MOVE")
        self.rb_wait  = Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "WAIT")
        self.rb_wake  = Gtk.RadioButton.new_with_label_from_widget(self.rb_click, "WAKE")

        # pack them
        for rb in (self.rb_click, self.rb_type, self.rb_scroll, self.rb_move, self.rb_wait, self.rb_wake):
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

        # TYPE params: large scrollable text area (wide + placeholder)
        self.type_view = Gtk.TextView()
        self.type_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.type_view.set_hexpand(True)
        self.type_view.set_vexpand(True)

        self.type_scroll = Gtk.ScrolledWindow()
        self.type_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.type_scroll.set_min_content_height(160)  # visible area; will grow wide
        self.type_scroll.set_hexpand(True)
        self.type_scroll.add(self.type_view)

        # WAIT params: seconds
        self.wait_entry = Gtk.Entry()
        self.wait_entry.set_placeholder_text("Seconds (e.g. 3.0)")

        # simple placeholder behavior for TextView
        self._type_placeholder_active = False
        self.type_view.connect("focus-in-event", self._on_type_focus_in)
        self.type_view.connect("focus-out-event", self._on_type_focus_out)
        self._ensure_type_placeholder()


        # SCROLL params: numeric entry with hint
        self.scroll_entry = Gtk.Entry()
        self.scroll_entry.set_placeholder_text("Scroll amount (e.g. -1 => ~down 100px)")

        # MOVE has no extra params for now (it's to a box region)
        # Initially, pack click controls (default)
        self.param_box.pack_start(Gtk.Label(label="Button:"), False, False, 0)
        self.param_box.pack_start(self.click_combo, False, False, 0)

        # Center radios & params nicely
        self.action_options_box.set_halign(Gtk.Align.CENTER)
        self.action_options_box.set_valign(Gtk.Align.CENTER)

        # --- Middle bottom controls row ---
        # Left (in middle): Delete Selection (disabled until selection active)
        self.delete_selection_btn = Gtk.Button(label="Delete Selection")
        self.delete_selection_btn.set_sensitive(False)
        self.delete_selection_btn.connect("clicked", self.on_delete_selection)
        self.delete_selection_btn.set_vexpand(False)
        self.delete_selection_btn.set_hexpand(False)

        left_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        left_controls.set_vexpand(False)
        left_controls.set_valign(Gtk.Align.END)  # sit at bottom of middle column
        left_controls.pack_start(self.delete_selection_btn, False, False, 0)

        self.add_btn = Gtk.Button(label=">>> Add to Queue >>>")
        self.add_btn.set_sensitive(False)  # disabled until a box is selected
        self.add_btn.connect("clicked", self.on_add_to_queue)

        self.remove_btn = Gtk.Button(label="Remove from Queue")
        self.remove_btn.connect("clicked", self.on_remove_from_queue)

        self.export_btn = Gtk.Button(label="Export JSON")
        self.export_btn.connect("clicked", self.on_export_json)

        self.load_btn = Gtk.Button(label="Load Plan…")
        self.load_btn.connect("clicked", self.on_load_plan)

        right_controls_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_controls_col.set_halign(Gtk.Align.END)
        right_controls_col.pack_start(self.add_btn, False, False, 0)
        right_controls_col.pack_start(self.remove_btn, False, False, 0)
        right_controls_col.pack_start(self.export_btn, False, False, 0)
        right_controls_col.pack_start(self.load_btn, False, False, 0)


        # --- Pi IP entry ---
        self.pi_ip_entry = Gtk.Entry()
        self.pi_ip_entry.set_placeholder_text("Pi IP (e.g., 192.168.1.214)")
        self.pi_ip_entry.set_text("192.168.1.214")  # default; change as needed


        # --- Run Act button ---
        self.run_act_btn = Gtk.Button(label="Run Act")
        self.run_act_btn.connect("clicked", self.on_run_act)

        # Add to right_controls_col (under Load/Export)
        right_controls_col.pack_start(self.pi_ip_entry, False, False, 0)
        right_controls_col.pack_start(self.run_act_btn, False, False, 0)


        # Row that holds left & right control groups
        middle_bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        middle_bottom_row.pack_start(left_controls, False, False, 0)

        # Pack the mini "next screenshot" panel first (to the right side),
        # then pack the right-controls last so they stay on the extreme right.
        middle_bottom_row.pack_end(right_controls_col, False, False, 0)


        # Assemble middle column (no "Action:" title)
        self.action_builder_box.pack_start(self.action_options_box, False, False, 0)
        self.action_builder_box.pack_start(self.param_box, True, True, 0)  # allow params to expand (esp. TYPE)
        self.action_builder_box.pack_end(middle_bottom_row, False, False, 0)

        # Middle column ~50%
        self.bottom_box.pack_start(self.action_builder_box, True, True, 0)


        # Right column: Action Queue (TreeView, reorderable) ~25%
        self.action_queue_store = Gtk.ListStore(int, str)  # (index, description)

        self.action_queue_view = Gtk.TreeView(model=self.action_queue_store)
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn("Queue", renderer, text=1)
        self.action_queue_view.append_column(col)
        self.action_queue_view.set_headers_visible(False)
        self.action_queue_view.set_reorderable(True)  # enable drag & drop reordering

        # selection -> highlight associated box
        self.queue_selection = self.action_queue_view.get_selection()
        self.queue_selection.connect("changed", self.on_queue_selection_changed)

        # When rows are reordered by DnD, sync back to self.action_queue
        self.action_queue_store.connect("rows-reordered", self.on_queue_rows_reordered)

        self.action_queue_scroll = Gtk.ScrolledWindow()
        self.action_queue_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.action_queue_scroll.set_min_content_height(220)
        self.action_queue_scroll.set_size_request(320, -1)  # matches your 25/50/25 width
        self.action_queue_scroll.add(self.action_queue_view)

        self.right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.right_col.set_size_request(320, -1)
        self.right_col.pack_start(self.action_queue_scroll, True, True, 0)

        self.bottom_box.pack_start(self.right_col, False, False, 0)


        # --- Overlay container for viewer + "next screenshot" panel ---
        self.overlay = Gtk.Overlay()
        self.overlay.add(self.screenshot_viewer)  # base layer

        # Mini "next screenshot" panel (hidden by default)
        self.next_panel = Gtk.EventBox(visible=False)
        panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        panel_box.set_margin_top(6)
        panel_box.set_margin_right(6)
        panel_box.set_margin_bottom(6)
        panel_box.set_margin_left(6)

        # Header row: label + X button
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.next_label = Gtk.Label(
            label="Next screenshot available — click to advance",
            xalign=0.0
        )
        close_btn = Gtk.Button.new_with_label("✕")
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", lambda *_: self.next_panel.set_visible(False))
        header.pack_start(self.next_label, True, True, 0)
        header.pack_end(close_btn, False, False, 0)

        # Thumbnail image
        self.next_thumb = Gtk.Image()

        panel_box.pack_start(header, False, False, 0)
        panel_box.pack_start(self.next_thumb, False, False, 0)
        self.next_panel.add(panel_box)
        self.next_panel.connect("button-press-event", self._on_next_panel_clicked)

        # Put panel at bottom-right of the overlay
        self.next_panel.set_halign(Gtk.Align.END)
        self.next_panel.set_valign(Gtk.Align.END)
        self.overlay.add_overlay(self.next_panel)

        # Main vbox: top overlay, bottom controls
        self.main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_vbox.pack_start(self.overlay, True, True, 0)
        self.main_vbox.pack_start(self.bottom_box, False, False, 0)
        self.main_vbox.set_hexpand(True)
        self.main_vbox.set_vexpand(True)


        # --- Screenshot run tracking (Phase-2) ---
        self.screens_root = Path("runs/screens")
        self.current_run_id = None
        self.current_shot_index = 0
        self._latest_meta_mtime = 0.0


        self.main_grid.attach(self.main_vbox, 0, 0, 1, 1)
        self._update_add_button_sensitivity()
        
        # Start polling for new stable shots (once/second)
        GLib.timeout_add_seconds(1, self._poll_for_new_shot)

    # Debug hook
    def on_box_drawn(self, widget, rect_dict):
        print(f"[DEBUG] Box drawn: {rect_dict}")

    # Called by viewer when a box is finalized
    def on_box_finalized(self, rect_dict, index):
        # rect_dict already has id (index). Use readable "Box N" naming.
        box_id = rect_dict['id']
        label_text = f"Box {box_id} x={rect_dict['x']} y={rect_dict['y']} w={rect_dict['width']} h={rect_dict['height']}"
        print(f"[DEBUG] Adding label: {label_text}")

        # create a new row and insert at top (newest first)
        row = Gtk.ListBoxRow()
        label = Gtk.Label(label=label_text, xalign=0)
        label.set_margin_top(2)
        label.set_margin_bottom(2)
        row.add(label)
        self.selection_list.insert(row, 0)
        self.selection_list.show_all()

        # auto-select it: select UI row + highlight/animate box
        self.selection_list.select_row(row)      # highlights in left column
        self.current_box_index = box_id          # controller state
        self.screenshot_viewer.select_box(box_id)  # starts dashed animation

        # enable buttons that require a selection
        try:
            self.delete_selection_btn.set_sensitive(True)
            self.add_btn.set_sensitive(True)
        except AttributeError:
            pass


    # Map selection list click to actual box index (we store boxes in viewer with ids == index)
    def on_selection_clicked(self, listbox, row):
        # Called when the selection list row changes (selected or cleared).
        if not row:
            self.current_box_index = None
            # disable selection-dependent buttons
            try:
                self.delete_selection_btn.set_sensitive(False)
                self.add_btn.set_sensitive(False)
            except AttributeError:
                pass
            self.screenshot_viewer.select_box(None)
            self._update_add_button_sensitivity()

            return

        # enable selection-dependent buttons
        try:
            self.delete_selection_btn.set_sensitive(True)
            self.add_btn.set_sensitive(True)
        except AttributeError:
            pass

        visual_index = list(self.selection_list.get_children()).index(row)
        # newest-first mapping -> compute actual id
        actual_index = len(self.screenshot_viewer.boxes) - 1 - visual_index
        self.current_box_index = actual_index
        print(f"[DEBUG] Selected visual={visual_index} -> actual={actual_index}")
        self.screenshot_viewer.select_box(actual_index)
        self._update_add_button_sensitivity()

    def on_delete_selection(self, btn):
        """Delete the currently selected bounding box and update UI + actions."""
        # Determine which visual row is selected
        sel_row = self.selection_list.get_selected_row()
        if not sel_row:
            print("[WARN] No selection to delete.")
            return

        # compute visual -> actual index
        visual_children = list(self.selection_list.get_children())
        try:
            visual_index = visual_children.index(sel_row)
        except ValueError:
            print("[WARN] Selected row not found among children.")
            return

        # actual index in screenshot_viewer.boxes
        actual_index = len(self.screenshot_viewer.boxes) - 1 - visual_index
        print(f"[DEBUG] Deleting Box {actual_index} (visual {visual_index})")

        # 1) Remove box from viewer
        try:
            del self.screenshot_viewer.boxes[actual_index]
        except Exception as e:
            print(f"[ERROR] Failed to delete box from viewer: {e}")

        # Reassign ids inside viewer.boxes so they match list indices
        for i, b in enumerate(self.screenshot_viewer.boxes):
            b['id'] = i

        # 2) Remove any actions that reference the deleted box,
        #    and remap higher box_ids downward by 1.
        new_action_queue = []
        for act in self.action_queue:
            bid = act.get("box_id")
            if bid is None:
                new_action_queue.append(act)
                continue
            if bid == actual_index:
                # drop this action (it referred to deleted box)
                print(f"[DEBUG] Dropping action referencing deleted Box {bid}: {act}")
                continue
            elif bid > actual_index:
                # remap downward
                act["box_id"] = bid - 1
            new_action_queue.append(act)
        self.action_queue = new_action_queue

        # 3) Rebuild selection_list (newest-first) so labels and order are consistent
        for child in list(self.selection_list.get_children()):
            self.selection_list.remove(child)
        # iterate boxes and insert newest-first
        for b in reversed(self.screenshot_viewer.boxes):
            bi = b['id']
            txt = f"Box {bi} x={b['x']} y={b['y']} w={b['width']} h={b['height']}"
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=txt, xalign=0)
            label.set_margin_top(2)
            label.set_margin_bottom(2)
            row.add(label)
            self.selection_list.add(row)
        self.selection_list.show_all()

        # 4) Clear current selection and UI highlights
        self.current_box_index = None
        self.screenshot_viewer.select_box(None)
        self.delete_selection_btn.set_sensitive(False)
        self.add_btn.set_sensitive(False)
        self._update_add_button_sensitivity()

        # 5) Refresh action queue UI
        self._update_action_queue_ui()


    # When user toggles which action is selected, swap parameter UI
    def on_action_radio_toggled(self, rb):
        if not rb.get_active():
            return
        # Clear param_box children
        for child in self.param_box.get_children():
            self.param_box.remove(child)

        # Add action-specific params
        if rb is self.rb_click:
            self.param_box.pack_start(Gtk.Label(label="Button:"), False, False, 0)
            self.param_box.pack_start(self.click_combo, False, False, 0)
        elif rb is self.rb_type:
            # just the big text area (no label)
            self.param_box.pack_start(self.type_scroll, True, True, 0)
        elif rb is self.rb_scroll:
            self.param_box.pack_start(Gtk.Label(label="Amount:"), False, False, 0)
            self.param_box.pack_start(self.scroll_entry, False, False, 0)
        elif rb is self.rb_move:
            self.param_box.pack_start(Gtk.Label(label="Move to selected box"), False, False, 0)
        elif rb is self.rb_wait:
            self.param_box.pack_start(Gtk.Label(label="Seconds:"), False, False, 0)
            self.param_box.pack_start(self.wait_entry, False, False, 0)
        elif rb is self.rb_wake:
            self.param_box.pack_start(Gtk.Label(label="Wake screen (wiggle)"), False, False, 0)

        self.param_box.show_all()
        self._update_add_button_sensitivity()

    def _action_requires_box(self):
        # Only CLICK and MOVE strictly require a selected box
        return self.rb_click.get_active() or self.rb_move.get_active()

    def _update_add_button_sensitivity(self):
        needs_box = self._action_requires_box()
        has_box = self.current_box_index is not None
        self.add_btn.set_sensitive((not needs_box) or has_box)

    def _ensure_type_placeholder(self):
        if self._type_placeholder_active:
            return
        buf = self.type_view.get_buffer()
        start, end = buf.get_start_iter(), buf.get_end_iter()
        if buf.get_text(start, end, True) == "":
            buf.set_text("type here…")
            self._type_placeholder_active = True

    def _on_type_focus_in(self, *a):
        if self._type_placeholder_active:
            self.type_view.get_buffer().set_text("")
            self._type_placeholder_active = False
        return False

    def _on_type_focus_out(self, *a):
        buf = self.type_view.get_buffer()
        start, end = buf.get_start_iter(), buf.get_end_iter()
        if buf.get_text(start, end, True) == "":
            self._ensure_type_placeholder()
        return False

    def _get_selected_action_type(self):
        if self.rb_click.get_active():  return "CLICK"
        if self.rb_type.get_active():   return "TYPE"
        if self.rb_scroll.get_active(): return "SCROLL"
        if self.rb_move.get_active():   return "MOVE"
        if self.rb_wait.get_active():   return "WAIT"
        if self.rb_wake.get_active():   return "WAKE"
        return "CLICK"


    # Add action to queue (associate with current_box_index)
    def on_add_to_queue(self, btn):
        # Only CLICK and MOVE truly require a selected box
        if self._action_requires_box() and self.current_box_index is None:
            print("[WARN] This action requires a selected box.")
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
            buf = self.type_view.get_buffer()
            start_iter, end_iter = buf.get_start_iter(), buf.get_end_iter()
            txt = buf.get_text(start_iter, end_iter, True)
            if self._type_placeholder_active or txt.strip() == "type here…":
                txt = ""
            action["params"]["text"] = txt
        elif action_type == "SCROLL":
            # allow numeric or textual value; caller can interpret
            action["params"]["amount"] = self.scroll_entry.get_text()
        elif action_type == "MOVE":
            # no params for move; destination is the box region itself
            pass
        elif action_type == "WAIT":
            try:
                secs = float(self.wait_entry.get_text().strip() or "0")
            except ValueError:
                secs = 0.0
            action["params"]["seconds"] = max(0.0, secs)
        elif action_type == "WAKE":
            # no params
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
        model, treeiter = self.queue_selection.get_selected()
        if not treeiter:
            print("[WARN] No queue selection to remove.")
            return
        idx = model[treeiter][0]
        if 0 <= idx < len(self.action_queue):
            removed = self.action_queue.pop(idx)
            print(f"[DEBUG] Removed action: {removed}")
            self._update_action_queue_ui()
        else:
            print("[WARN] Invalid index selected for removal.")


    def on_queue_selection_changed(self, selection):
        model, treeiter = selection.get_selected()
        if not treeiter:
            return
        idx = model[treeiter][0]  # our index column
        if 0 <= idx < len(self.action_queue):
            act = self.action_queue[idx]
            box_id = act.get("box_id")
            if box_id is not None and 0 <= box_id < len(self.screenshot_viewer.boxes):
                self.screenshot_viewer.select_box(box_id)
            print(f"[DEBUG] Queue selection idx={idx}: {act}")

    def on_queue_rows_reordered(self, model, path, iter, new_order):
        """
        new_order: list mapping old positions -> new positions.
        We apply this to self.action_queue and then rebuild indices.
        """
        if not new_order or len(new_order) != len(self.action_queue):
            return
        new_list = [None] * len(self.action_queue)
        for old_pos, new_pos in enumerate(new_order):
            new_list[new_pos] = self.action_queue[old_pos]
        self.action_queue = new_list
        self._update_action_queue_ui()
        print("[DEBUG] Action queue reordered via DnD.")

    def on_load_plan(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Load UI Export (boxes & actions)",
            parent=self.window,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN, Gtk.ResponseType.OK
            )
        )
        json_filter = Gtk.FileFilter()
        json_filter.set_name("JSON files")
        json_filter.add_pattern("*.json")
        dialog.add_filter(json_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if not path:
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)
            boxes = data.get("boxes", [])
            actions = data.get("actions", [])
            if not isinstance(boxes, list) or not isinstance(actions, list):
                raise ValueError("Invalid JSON: 'boxes' and 'actions' must be lists.")
        except Exception as e:
            print(f"[ERROR] Failed to load plan: {e}")
            return

        # Load boxes into viewer
        self.screenshot_viewer.boxes = []
        for i, b in enumerate(boxes):
            # normalize / ensure ids are sequential
            nb = {
                "id": i,
                "x": int(b.get("x", 0)),
                "y": int(b.get("y", 0)),
                "width": int(b.get("width", 1)),
                "height": int(b.get("height", 1)),
            }
            self.screenshot_viewer.boxes.append(nb)

        # Rebuild left list (newest-first)
        for child in list(self.selection_list.get_children()):
            self.selection_list.remove(child)
        for b in reversed(self.screenshot_viewer.boxes):
            bi = b['id']
            txt = f"Box {bi} x={b['x']} y={b['y']} w={b['width']} h={b['height']}"
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=txt, xalign=0)
            label.set_margin_top(2)
            label.set_margin_bottom(2)
            row.add(label)
            self.selection_list.add(row)
        self.selection_list.show_all()

        # Load actions
        self.action_queue = list(actions)
        self._update_action_queue_ui()

        # Clear selection states
        self.current_box_index = None
        self.screenshot_viewer.select_box(None)
        self.delete_selection_btn.set_sensitive(False)
        self.add_btn.set_sensitive(False)
        self._update_add_button_sensitivity()

        print(f"[INFO] Loaded {len(boxes)} boxes and {len(actions)} actions from {path}")

    def _update_action_queue_ui(self):
        # rebuild the store from self.action_queue
        self.action_queue_store.clear()
        for i, act in enumerate(self.action_queue):
            # Build desc
            box_ref = act.get('box_id', '?')
            if box_ref != '?':
                box_ref_str = f"Box {box_ref}"
            else:
                box_ref_str = "Box ?"

            if act['type'] == "WAIT":
                desc = f"[{i}] WAIT ({act['params'].get('seconds', 0)}s)"
            elif act['type'] == "WAKE":
                desc = f"[{i}] WAKE (wiggle)"
            else:
                desc = f"[{i}] {act['type']} on {box_ref_str}"
                if act['type'] == "CLICK":
                    desc += f" ({act['params'].get('button','Left')})"
                elif act['type'] == "TYPE":
                    short = (act['params'].get('text','') or '')[:40]
                    desc += f' ("{short}")'
                elif act['type'] == "SCROLL":
                    desc += f" (amt={act['params'].get('amount','')})"
                elif act['type'] == "MOVE":
                    if "from" in act and "to" in act:
                        desc += f" from {act['from']} -> {act['to']} (d={act.get('duration_ms')})"
            if act.get("generated"):
                desc = "(auto) " + desc

            self.action_queue_store.append([i, desc])


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
    def _read_current_run_id(self):
        f = self.screens_root / "current_run.txt"
        if not f.exists():
            return None
        try:
            return f.read_text().strip()
        except Exception:
            return None

    def _load_grayscale_thumb(self, path: Path, scale=0.5) -> GdkPixbuf.Pixbuf:
        # Load original
        pb = GdkPixbuf.Pixbuf.new_from_file(str(path))
        # Convert to grayscale via saturate_and_pixelate (sat=0)
        gray = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, pb.get_has_alpha(), pb.get_bits_per_sample(),
                                    pb.get_width(), pb.get_height())
        pb.saturate_and_pixelate(gray, 0.0, False)
        # Scale
        w = int(gray.get_width() * scale)
        h = int(gray.get_height() * scale)
        if w < 1 or h < 1:
            w, h = max(1, w), max(1, h)
        scaled = gray.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        return scaled

    def _poll_for_new_shot(self):
        # 1) check run id
        run_id = self._read_current_run_id()
        if not run_id:
            # hide panel if no run
            if self.next_panel.get_visible():
                self.next_panel.set_visible(False)
            return True

        # 2) read latest.json and mtime (avoid reprocessing same file)
        run_dir = self.screens_root / run_id
        latest_meta = run_dir / "latest.json"
        if not latest_meta.exists():
            return True

        try:
            st = latest_meta.stat()
        except Exception:
            return True

        if st.st_mtime <= self._latest_meta_mtime:
            return True  # nothing new

        # something changed; parse it
        try:
            obj = json.loads(latest_meta.read_text())
            latest_idx = int(obj.get("latest_index", 0))
            latest_path = Path(obj.get("path", ""))
        except Exception:
            return True

        self._latest_meta_mtime = st.st_mtime
        self.current_run_id = run_id

        if latest_idx > self.current_shot_index and latest_path.exists():
            # prepare thumbnail and show panel
            try:
                thumb = self._load_grayscale_thumb(latest_path, scale=0.25)
                self.next_thumb.set_from_pixbuf(thumb)
                self.next_panel.set_visible(True)
                # stash target path on the widget for click handler
                self._next_image_path = latest_path
                self._next_index_value = latest_idx
            except Exception as e:
                print(f"[WARN] Failed to load next thumbnail: {e}")

        return True  # keep polling

    def _on_next_panel_clicked(self, *a):
        # Load the pending image into the main viewer and hide the panel
        if getattr(self, "_next_image_path", None):
            try:
                self.screenshot_viewer.load_image(str(self._next_image_path))
                self.current_shot_index = getattr(self, "_next_index_value", self.current_shot_index)

                # New act context: clear current action queue and re-enable Run Act
                self.action_queue = []
                self._update_action_queue_ui()
                self.run_act_btn.set_sensitive(True)

            except Exception as e:
                print(f"[WARN] Failed to load next screenshot: {e}")
        self.next_panel.set_visible(False)

    def _vm_send_ctl(self, vm_ip: str, port: int, payload: dict, timeout=2.0):
        try:
            with socket.create_connection((vm_ip, port), timeout=timeout) as s:
                s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                _ = s.recv(1024)
            return True
        except Exception as e:
            print(f"[WARN] VM control send failed: {e}")
            return False
    def _send_current_act_to_pi(self):
        """
        Expand self.action_queue to low-level actions with Humanizer and send to Pi.
        Returns the Pi reply dict or raises.
        """
        from handuz import Humanizer
        import zmq

        # Bind to current screenshot context
        ctx_run = self.current_run_id
        ctx_idx = self.current_shot_index
        if not ctx_run:
            raise RuntimeError("No run_id bound; wait for a screenshot.")
        # Build high-level plan payload (optional: save alongside)
        payload = {
            "run_id": ctx_run,
            "shot_index": ctx_idx,
            "boxes": list(self.screenshot_viewer.boxes),
            "actions": list(self.action_queue),
            "created_at": int(time.time())
        }

        # Expand to low-level
        h = Humanizer()
        final_actions = []

        def flush_h():
            if h.action_plan:
                final_actions.extend(h.action_plan)
                h.clear_plan()

        # helper: center of a box
        def center(b): return (b['x'] + b['width'] // 2, b['y'] + b['height'] // 2)

        for act in self.action_queue:
            atype = act.get("type")
            box_id = act.get("box_id")
            params = act.get("params", {}) or {}

            if atype == "WAKE":
                h.wake_up_screen(); flush_h()
            elif atype == "WAIT":
                secs = float(params.get("seconds", 0) or 0)
                final_actions.append(["PAUSE", secs])
            elif atype == "MOVE":
                if box_id is None or not (0 <= box_id < len(self.screenshot_viewer.boxes)):
                    continue
                x, y = center(self.screenshot_viewer.boxes[box_id])
                h.move_to(x, y); flush_h()
            elif atype == "CLICK":
                btn = (params.get("button") or "Left").upper()
                btn = {"LEFT":"LEFT","RIGHT":"RIGHT","MIDDLE":"MIDDLE"}.get(btn,"LEFT")
                h.click(btn); flush_h()
            elif atype == "TYPE":
                txt = (params.get("text","") or "").replace("{ENTER}", "\n")
                h.type_text(txt); flush_h()
            elif atype == "SCROLL":
                amt_raw = params.get("amount", 0)
                try: amt = int(amt_raw)
                except: amt = int(str(amt_raw).strip() or 0)
                h.scroll(amt); flush_h()

        # Send to Pi (REQ/REP)
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect(f"tcp://{PI_ADDR}:{PI_PORT}")
        sock.send_string(json.dumps(final_actions))
        reply = json.loads(sock.recv_string())
        return reply, payload, final_actions

    def vm_mute(self, vm_ip: str, ms: int = 120000):
        return self._vm_send_ctl(vm_ip, 5002, {"cmd": "mute", "ms": ms})

    def vm_unmute(self, vm_ip: str):
        return self._vm_send_ctl(vm_ip, 5002, {"cmd": "unmute"})

    def on_export_json(self, btn):
        import os, datetime
        os.makedirs("runs/ui_exports", exist_ok=True)

        payload = {
            "boxes": list(self.screenshot_viewer.boxes),
            "actions": list(self.action_queue)
        }
        j = json.dumps(payload, indent=2)

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"runs/ui_exports/ui_export_{ts}.json"

        with open(out_path, "w") as f:
            f.write(j)

        print(f"[INFO] Exported UI actions to {out_path}")
    def on_run_act(self, btn):
        """
        Export current UI plan and execute via run_plan.py.
        Host does not talk to the VM control server; the Pi mutes/unmutes.
        """
        if not self.action_queue:
            print("[WARN] Nothing in action queue.")
            return

        import os, datetime
        os.makedirs("runs/ui_exports", exist_ok=True)

        payload = {
            "boxes": list(self.screenshot_viewer.boxes),
            "actions": list(self.action_queue)
        }
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_path = Path(f"runs/ui_exports/ui_export_{ts}.json")
        plan_path.write_text(json.dumps(payload, indent=2))
        print(f"[INFO] Exported current plan to {plan_path}")

        # Get Pi IP from the UI
        pi_ip = self.pi_ip_entry.get_text().strip()
        if not pi_ip:
            print("[ERROR] Pi IP is required.")
            return

        # Disable until next screenshot is accepted
        self.run_act_btn.set_sensitive(False)

        # Invoke run_plan.py synchronously
        try:
            run_plan_py = Path(__file__).resolve().parent.parent / "run_plan.py"
            cmd = ["python3", str(run_plan_py),
                "--plan", str(plan_path),
                "--pi", pi_ip,
                "--logs", "runs/logs"]
            print("[INFO] Running:", " ".join(cmd))
            subprocess.run(cmd, check=True)
            print("[INFO] Plan sent to Pi. Waiting for next stabilized screenshot...")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] run_plan failed with exit code {e.returncode}")
            self.run_act_btn.set_sensitive(True)
        except Exception as e:
            print(f"[ERROR] Could not execute run_plan: {e}")
            self.run_act_btn.set_sensitive(True)


    # run
    def run(self):
        self.screenshot_viewer.load_image("gui/recv_screen.png")
        self.window.show_all()
        Gtk.main()

if __name__ == "__main__":
    app = HostUI()
    app.run()
