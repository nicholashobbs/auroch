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

        # --- ML overlay state ---
        self.ui_graph = None
        self.show_viewport  = False
        self.show_containers= True
        self.show_inputs    = True
        self.show_buttons   = True
        self.show_links     = True
        self.show_ocr       = True
        self.show_minimap   = False

    def load_image(self, image_path):
        print(f"DEBUG: 3. load_image called for '{image_path}'.")
        try:
            self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
            w = self.pixbuf.get_width()
            h = self.pixbuf.get_height()
            self.set_size_request(w, h)

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
        self._draw_ml_overlays(cr)
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

    def clear_all_annotations(self):
        """
        Remove all user-drawn boxes/overlays for a fresh act.
        """
        try:
            self.boxes = []
        except Exception:
            pass
        self.selected_index = None
        self._stop_dash_timer()
        self.queue_draw()

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
    def set_ui_graph(self, graph: dict):
        self.ui_graph = graph or {}
        self.queue_draw()

    def set_layer_visibility(self, kind: str, value: bool):
        if   kind == "viewport":   self.show_viewport = bool(value)
        elif kind == "containers": self.show_containers = bool(value)
        elif kind == "inputs":     self.show_inputs = bool(value)
        elif kind == "buttons":    self.show_buttons = bool(value)
        elif kind == "links":      self.show_links = bool(value)
        elif kind == "ocr":        self.show_ocr = bool(value)
        self.queue_draw()

    def set_minimap(self, on: bool):
        self.show_minimap = bool(on)
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
    def _draw_translucent_rects(self, cr, rects, rgba, line_width=2.0):
        # rgba: (r,g,b,a) in [0..1]
        r,g,b,a = rgba
        cr.set_source_rgba(r,g,b,a)
        for b in rects:
            x1,y1,x2,y2 = b
            cr.rectangle(x1, y1, x2-x1, y2-y1)
            cr.fill_preserve()
            cr.set_line_width(line_width)
            cr.stroke()

    def _draw_gray_stipple(self, cr, rects):
        if not rects: return
        # create a small dot pattern
        import cairo
        pat_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
        ctx = cairo.Context(pat_surf)
        ctx.set_source_rgba(0.5,0.5,0.5,0.25)  # light gray, low alpha
        ctx.arc(2,2,1.5,0,6.283); ctx.fill()
        ctx.arc(6,6,1.5,0,6.283); ctx.fill()
        pattern = cairo.SurfacePattern(pat_surf)
        pattern.set_extend(cairo.EXTEND_REPEAT)
        cr.set_source(pattern)
        # paint over each rect with pattern (use clip)
        for b in rects:
            x1,y1,x2,y2 = b
            cr.save()
            cr.rectangle(x1, y1, x2-x1, y2-y1)
            cr.clip()
            cr.paint_with_alpha(0.65)
            cr.restore()

    def _draw_viewport_mask(self, cr, full_w, full_h, keep_bbox):
        # Darken outside keep_bbox, plus diagonal hatch
        import cairo, math
        x1,y1,x2,y2 = keep_bbox
        # darken outside
        cr.save()
        cr.set_source_rgba(0,0,0,0.35)
        cr.rectangle(0,0,full_w, full_h)
        # clear keep area
        cr.rectangle(x1,y1,x2-x1,y2-y1)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.fill()
        cr.restore()
        # cross hatch
        cr.save()
        cr.set_source_rgba(0,0,0,0.10)
        cr.set_line_width(1.0)
        step = 16
        # Diagonals (\/)
        for d in range(-full_h, full_w, step):
            cr.move_to(max(0,d), max(0,-d))
            cr.line_to(min(full_w, d+full_h), min(full_h, full_h-d))
        cr.stroke()
        cr.restore()

    def _draw_minimap(self, cr, W, H):
        # White overlay, 75% opacity, then draw elements scaled 1:1 (we're already in image coords)
        cr.save()
        cr.set_source_rgba(1,1,1,0.75)
        cr.rectangle(0,0,W,H)
        cr.fill()
        # Draw containers/elements/ocr words outlines + small text
        graph = self.ui_graph or {}
        import cairo
        # Containers (medium gray)
        conts = (graph.get("containers") or [])
        self._draw_translucent_rects(cr, [c["bbox"] for c in conts], (0.5,0.5,0.5,0.35), line_width=2.0)
        # Inputs (red), Buttons (green), Links (blue)
        elems = (graph.get("elements") or [])
        reds  = [e["bbox"] for e in elems if e.get("role")=="input"]
        greens= [e["bbox"] for e in elems if e.get("role")=="button"]
        blues = [e["bbox"] for e in elems if e.get("role")=="link_like"]
        self._draw_translucent_rects(cr, reds,   (1.0,0.0,0.0,0.30), line_width=2.0)
        self._draw_translucent_rects(cr, greens, (0.0,1.0,0.0,0.30), line_width=2.0)
        self._draw_translucent_rects(cr, blues,  (0.0,0.4,1.0,0.30), line_width=2.0)
        # OCR words: print tiny text
        ocrw = ((graph.get("ocr") or {}).get("words") or [])
        cr.set_source_rgba(0,0,0,0.9)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(10.0)
        for w in ocrw[:1200]:
            x1,y1,x2,y2 = w["bbox"]
            txt = w.get("text","")
            if not txt: continue
            cr.move_to(x1+2, y1+12)
            cr.show_text(txt[:32])
        cr.restore()

    def _draw_ml_overlays(self, cr):
        # Early out if no graph
        graph = self.ui_graph or {}
        if not graph: return
        W = int(graph.get("image_size",{}).get("w", 0) or 0)
        H = int(graph.get("image_size",{}).get("h", 0) or 0)
        if W <= 0 or H <= 0: return

        # Minimap mode supersedes normal overlay drawing
        if self.show_minimap:
            self._draw_minimap(cr, W, H)
            return

        # Viewport mask
        if self.show_viewport:
            vp = (graph.get("viewport") or {}).get("bbox", [0,0,W,H])
            self._draw_viewport_mask(cr, W, H, vp)

        # Containers
        if self.show_containers:
            conts = (graph.get("containers") or [])
            self._draw_translucent_rects(cr, [c["bbox"] for c in conts], (0.5,0.5,0.5,0.35), line_width=2.0)

        elems = (graph.get("elements") or [])
        # Inputs (red)
        if self.show_inputs:
            rects = [e["bbox"] for e in elems if e.get("role")=="input"]
            self._draw_translucent_rects(cr, rects, (1.0,0.0,0.0,0.30), line_width=2.0)
        # Buttons (green)
        if self.show_buttons:
            rects = [e["bbox"] for e in elems if e.get("role")=="button"]
            self._draw_translucent_rects(cr, rects, (0.0,1.0,0.0,0.30), line_width=2.0)
        # Links (blue)
        if self.show_links:
            rects = [e["bbox"] for e in elems if e.get("role")=="link_like"]
            self._draw_translucent_rects(cr, rects, (0.0,0.4,1.0,0.30), line_width=2.0)

        # OCR stipple
        if self.show_ocr:
            ocrw = ((graph.get("ocr") or {}).get("words") or [])
            rects = [w["bbox"] for w in ocrw]
            self._draw_gray_stipple(cr, rects)

GObject.type_register(ScreenshotViewer)
