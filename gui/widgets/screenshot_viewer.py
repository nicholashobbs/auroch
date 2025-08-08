# ~/auroch/gui/widgets/screenshot_viewer.py
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, GObject

class ScreenshotViewer(Gtk.DrawingArea):
    """A widget that displays an image and allows drawing a bounding box."""
    
    __gsignals__ = {
        'box-drawn': (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,))
    }

    def __init__(self):
        super().__init__()
        self.pixbuf = None
        self.start_x, self.start_y = 0, 0
        self.end_x, self.end_y = 0, 0
        self.drawing = False
        self.rect = None

        print("DEBUG: 1. ScreenshotViewer __init__ called.")
        
        # We must have our own window to receive events
        self.set_can_focus(True)
        self.set_focus_on_click(True)

        # Connect the Gtk signals to our handler methods
        self.connect("draw", self.on_draw)
        self.connect("button_press_event", self.on_button_press)
        self.connect("button_release_event", self.on_button_release)
        self.connect("motion_notify_event", self.on_motion_notify)
        
        # Explicitly tell the widget which events to listen for
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )

        self.connect("realize", lambda *a: print("DEBUG: Widget realized"))
        # Ensure timer is stopped if widget is destroyed
        self.connect("destroy", lambda *a: self._stop_dash_timer())

        # store all completed boxes as dicts: {id, x, y, width, height}
        self.boxes = []
        self.selected_index = None     # index in self.boxes that is highlighted
        self.selection_callback = None # function(host_ui) called with (rect_dict, index)

        # Animated dash state
        self.dash_offset = 0.0               # moving offset used for selected box dashes
        self._dash_timer_id = None           # GLib timer source id
        self._dash_interval_ms = 60         # update interval in ms (about ~16 FPS)

    def load_image(self, image_path):
        print(f"DEBUG: 3. load_image called for '{image_path}'.")
        try:
            self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
            self.queue_draw()
            return True
        except GLib.Error as e:
            print(f"Error loading image: {e}")
            return False

    def on_draw(self, widget, cr):
        allocation = self.get_allocation()

        # White background (in case image is smaller)
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.rectangle(0, 0, allocation.width, allocation.height)
        cr.fill()

        # Draw screenshot
        if self.pixbuf:
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()

        # Draw finalized boxes:
        # To improve visibility over variable backgrounds, draw a darker shadow stroke
        # then draw the dashed (white-ish) stroke on top. Selected box has animated dash.
        for i, rect in enumerate(self.boxes):
            x, y, w, h = rect['x'], rect['y'], rect['width'], rect['height']

            # DRAW SHADOW (behind dashed stroke) for contrast
            cr.set_line_width(6.0)
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.35)  # translucent black shadow
            cr.rectangle(x, y, w, h)
            cr.stroke()

            # Draw dashed outline
            if i == self.selected_index:
                # Selected: brighter + animated dash offset
                dash_pattern = [12.0, 6.0]
                cr.set_line_width(3.0)
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)  # bright white
                cr.set_dash(dash_pattern, self.dash_offset)
                cr.rectangle(x, y, w, h)
                cr.stroke()
                cr.set_dash([], 0)  # clear
            else:
                # Unselected: lighter dashed border (static)
                dash_pattern = [6.0, 6.0]
                cr.set_line_width(2.0)
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.75)
                cr.set_dash(dash_pattern, 0.0)
                cr.rectangle(x, y, w, h)
                cr.stroke()
                cr.set_dash([], 0)

        # Draw the active (being-drawn) box in translucent red on top of everything
        if self.drawing:
            rect = self.get_selection_rectangle()
            if rect:
                cr.set_source_rgba(1.0, 0.0, 0.0, 0.3)
                cr.rectangle(rect['x'], rect['y'], rect['width'], rect['height'])
                cr.fill()

        return True

    def on_button_press(self, widget, event):
        if event.button == 1:
            self.drawing = True
            self.start_x = event.x
            self.start_y = event.y
            self.end_x = event.x
            self.end_y = event.y
            self.queue_draw()

    def on_motion_notify(self, widget, event):
        """Called when the mouse is dragged."""
        if not self.drawing:
            return False

        self.end_x, self.end_y = event.x, event.y

        self.rect = {
            'x': int(min(self.start_x, self.end_x)),
            'y': int(min(self.start_y, self.end_y)),
            'width': max(1, int(abs(self.end_x - self.start_x))),
            'height': max(1, int(abs(self.end_y - self.start_y))),
        }

        self.queue_draw()
        return True

    def on_button_release(self, widget, event):
        if event.button == Gdk.BUTTON_PRIMARY and self.drawing:
            self.end_x, self.end_y = event.x, event.y

            self.rect = self.get_selection_rectangle()
            print(f"[DEBUG] on_button_release: widget={widget.get_name()} "
                  f"type={event.type} button={event.button} x={event.x} y={event.y}")
            print(f"[DEBUG] drawing={self.drawing}, rect={self.rect}")

            self.drawing = False

            if self.rect:
                new_box = self.rect.copy()
                new_box['id'] = len(self.boxes)
                self.boxes.append(new_box)
                if self.selection_callback:
                    self.selection_callback(new_box.copy(), new_box['id'])
                self.emit("box-drawn", new_box)

            self.queue_draw()
            return True
        return False

    def get_selection_rectangle(self):
        x = int(min(self.start_x, self.end_x))
        y = int(min(self.start_y, self.end_y))
        width = int(abs(self.start_x - self.end_x))
        height = int(abs(self.start_y - self.end_y))

        if width == 0:
            width = 1
        if height == 0:
            height = 1

        return {'x': x, 'y': y, 'width': width, 'height': height}

    def select_box(self, index):
        """Highlight a given box visually (index is 0..len(self.boxes)-1)."""
        # validate new selection
        if index is None or index < 0 or index >= len(self.boxes):
            self.selected_index = None
            self._stop_dash_timer()
        else:
            self.selected_index = index
            # ensure dash animation is running
            self._start_dash_timer()
        # reset dash offset so animation is consistent on new selection
        self.dash_offset = 0.0
        self.queue_draw()

    # ---- Animation helpers ----
    def _on_dash_tick(self):
        # Advance offset — value chosen to give smooth visible motion; tune as desired
        self.dash_offset += 4.0
        # keep offset bounded (optional)
        if self.dash_offset > 10000:
            self.dash_offset = self.dash_offset % 1000
        self.queue_draw()
        return True  # continue calling

    def _start_dash_timer(self):
        if self._dash_timer_id is None:
            self._dash_timer_id = GLib.timeout_add(self._dash_interval_ms, self._on_dash_tick)
            # immediate queue_draw to reflect starting state
            self.queue_draw()

    def _stop_dash_timer(self):
        if self._dash_timer_id is not None:
            try:
                GLib.source_remove(self._dash_timer_id)
            except Exception:
                pass
            self._dash_timer_id = None

GObject.type_register(ScreenshotViewer)
