# ~/auroch/gui/widgets/action_queue_view.py
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from data_structures import Action

class ActionQueueView(Gtk.ListBox):
    def __init__(self):
        super().__init__()
        self.actions = []

    def add_action(self, action: Action):
        """Adds a new action to the internal list and the UI."""
        self.actions.append(action)

        # Create a new row for the ListBox
        row_text = f"[{len(self.actions)}] {action.action_type}: {action.value or action.target_bbox}"
        row = Gtk.ListBoxRow()
        row.add(Gtk.Label(label=row_text, xalign=0))
        self.add(row)
        self.show_all()