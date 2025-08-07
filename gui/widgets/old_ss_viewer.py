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
        self.set_app_paintable(True)
        self.set_can_focus(True)
        self.set_focus_on_click(True)
        #self.set_events(self.get_events() | Gdk.EventMask.ALL_EVENTS_MASK)


        # Connect the Gtk signals to our handler methods
        self.connect("draw", self.on_draw)
        self.connect("button_press_event", self.on_button_press)
        self.connect("button_release_event", self.on_button_release)
        self.connect("motion_notify_event", self.on_motion_notify)
        
        # Explicitly tell the widget which events to listen for
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                Gdk.EventMask.BUTTON_RELEASE_MASK |
                Gdk.EventMask.POINTER_MOTION_MASK)

        self.connect("realize", lambda *a: print("DEBUG: Widget realized"))


    def load_image(self, image_path):
        print(f"DEBUG: 3. load_image called for '{image_path}'.")
        # ... (rest of the method is unchanged) ...
        try:
            self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
            self.queue_draw(); return True
        except GLib.Error as e:
            print(f"Error loading image: {e}"); return False

    def on_draw(self, widget, cr):
        allocation = self.get_allocation()

        # First, draw the white background
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.rectangle(0, 0, allocation.width, allocation.height)
        cr.fill()

        # Then draw the screenshot image (on top)
        if self.pixbuf:
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()

        # Now draw a green test box
        cr.set_source_rgba(0.0, 1.0, 0.0, 0.5)
        cr.rectangle(100, 100, 100, 100)
        cr.fill()

        # Draw selection box if we're drawing
        if self.drawing:
            rect = self.get_selection_rectangle()
            if rect:
                cr.set_source_rgba(1.0, 0.0, 0.0, 0.3)
                cr.rectangle(rect['x'], rect['y'], rect['width'], rect['height'])
                cr.fill()

        return True



    def on_button_press(self, widget, event):
        """Called when the mouse button is clicked down."""
        if event.button == Gdk.BUTTON_PRIMARY:
            self.drawing = True
            self.start_x, self.start_y = event.x, event.y
            self.end_x, self.end_y = event.x, event.y
        return True 

    def on_motion_notify(self, widget, event):
        """Called when the mouse is dragged."""
        if not self.drawing:
            return False  # or None; means no event handled

        # Update current mouse position
        self.end_x, self.end_y = event.x, event.y

        # Update the selection rectangle dict
        self.rect = {
            'x': int(min(self.start_x, self.end_x)),
            'y': int(min(self.start_y, self.end_y)),
            'width': max(1, int(abs(self.end_x - self.start_x))),
            'height': max(1, int(abs(self.end_y - self.start_y))),
        }

        # Request redraw
        self.queue_draw()
        return True

    def on_button_release(self, widget, event):
        """Called when the mouse button is released."""
        if not self.drawing:
            return
        if event.button == Gdk.BUTTON_PRIMARY and self.drawing:
            self.drawing = False
            rect = self.get_selection_rectangle()
            if self.rect is not None:
                self.emit("box-drawn", [rect['x'], rect['y'], rect['width'], rect['height']])
                print(f"{rect['x']}, {rect['y']}, {rect['width']}, {rect['height']}")
            else:
                print("[WARNING] on button release called, self.rect is None")
            self.queue_draw()
            print(f"on_button_release at ({event.x}, {event.y})")
        return True

    def get_selection_rectangle(self):
        x = int(min(self.start_x, self.end_x))
        y = int(min(self.start_y, self.end_y))
        width = int(abs(self.start_x - self.end_x))
        height = int(abs(self.start_y - self.end_y))

        if width == 0:
            width = 1
        if height == 0:
            height = 1

        # Return a simple dict
        return {'x': x, 'y': y, 'width': width, 'height': height}

GObject.type_register(ScreenshotViewer)