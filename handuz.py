import sys
import random
import numpy as np
import struct
import time
import matplotlib.pyplot as plt
import argparse
import json

# HID Scancode mapping for a standard US QWERTY layout
KEYCODE_MAP = {
    'a': 0x04, 'b': 0x05, 'c': 0x06, 'd': 0x07, 'e': 0x08, 'f': 0x09,
    'g': 0x0A, 'h': 0x0B, 'i': 0x0C, 'j': 0x0D, 'k': 0x0E, 'l': 0x0F,
    'm': 0x10, 'n': 0x11, 'o': 0x12, 'p': 0x13, 'q': 0x14, 'r': 0x15,
    's': 0x16, 't': 0x17, 'u': 0x18, 'v': 0x19, 'w': 0x1A, 'x': 0x1B,
    'y': 0x1C, 'z': 0x1D, '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21,
    '5': 0x22, '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
    '\n': 0x28, ' ': 0x2C, '-': 0x2D, '=': 0x2E, '[': 0x2F, ']': 0x30,
    '\\': 0x31, ';': 0x33, "'": 0x34, '`': 0x35, ',': 0x36, '.': 0x37,
    '/': 0x38
}

# Shift modifier is required for these characters
SHIFT_MAP = {
    'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'E': 'e', 'F': 'f',
    'G': 'g', 'H': 'h', 'I': 'i', 'J': 'j', 'K': 'k', 'L': 'l',
    'M': 'm', 'N': 'n', 'O': 'o', 'P': 'p', 'Q': 'q', 'R': 'r',
    'S': 's', 'T': 't', 'U': 'u', 'V': 'v', 'W': 'w', 'X': 'x',
    'Y': 'y', 'Z': 'z', '!': '1', '@': '2', '#': '3', '$': '4',
    '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\', ':': ';',
    '"': "'", '~': '`', '<': ',', '>': '.', '?': '/'
}

class Humanizer:
    def __init__(self, screen_width=1280, screen_height=800):
        self.config = {
            "SCREEN_WIDTH": screen_width,
            "SCREEN_HEIGHT": screen_height,
            # THE FIX: Drastically reduced speed for a ~10-second cross-screen move
            "AVG_PIXELS_PER_SECOND": 150, 
            "START_SPEED_MULTIPLIER": 1.5,
            "END_SPEED_MULTIPLIER": 0.5,
            "FRACTAL_DEPTH": 2,
            "MAIN_DETOURS_WEIGHTS": {1: 0.8, 2: 0.15, 3: 0.05},
            "SUB_DETOURS_WEIGHTS": {2: 0.8, 3: 0.15, 4: 0.05},
            "DETOUR_MU": 1.0,
            "DETOUR_SIGMA": 1.5,
        }
        self.current_x = 0
        self.current_y = 0
        self.action_plan = []

    def clear_plan(self):
        """Clears the current action plan but preserves the cursor position."""
        self.action_plan = []
    def _add_action(self, action_tuple):
        self.action_plan.append(action_tuple)
    def _get_detour_distance(self, segment_length):
        detour = np.random.lognormal(mean=self.config['DETOUR_MU'], sigma=self.config['DETOUR_SIGMA'])
        return min(detour, segment_length * 0.8)
    def _generate_fractal_path(self, start_point, end_point, depth):
        if depth == 0: return [np.array(end_point)]
        detour_weights = self.config['MAIN_DETOURS_WEIGHTS'] if depth == self.config['FRACTAL_DEPTH'] else self.config['SUB_DETOURS_WEIGHTS']
        num_detours = int(random.choices(list(detour_weights.keys()), weights=list(detour_weights.values()))[0])
        waypoints = [np.array(start_point)]
        for i in range(1, num_detours + 1):
            t = i / (num_detours + 1)
            line_point = np.array(start_point) * (1 - t) + np.array(end_point) * t
            segment_vec = np.array(end_point) - np.array(start_point)
            perp_vec = np.array([-segment_vec[1], segment_vec[0]])
            if np.linalg.norm(perp_vec) > 0: perp_vec = perp_vec / np.linalg.norm(perp_vec)
            detour_dist = self._get_detour_distance(np.linalg.norm(segment_vec))
            detour_dir = random.choice([-1, 1])
            detour_point = line_point + perp_vec * detour_dist * detour_dir
            detour_point[0] = np.clip(detour_point[0], 0, self.config['SCREEN_WIDTH'] - 1)
            detour_point[1] = np.clip(detour_point[1], 0, self.config['SCREEN_HEIGHT'] - 1)
            waypoints.append(detour_point)
        waypoints.append(np.array(end_point))
        final_path = [np.array(start_point)]
        for i in range(len(waypoints) - 1):
            sub_path = self._generate_fractal_path(waypoints[i], waypoints[i+1], depth - 1)
            final_path.extend(sub_path)
        return final_path
    def _interpolate_waypoints(self, waypoints):
        full_path = []
        for i in range(len(waypoints) - 1):
            start, end = waypoints[i], waypoints[i+1]
            dist = np.linalg.norm(end - start)
            num_steps = max(2, int(dist / 5))
            interpolated_segment = np.array([np.linspace(start[j], end[j], num_steps) for j in range(2)]).T
            full_path.extend(interpolated_segment)
        return full_path
    def _add_precision_and_noise(self, path):
        final_destination = path[-1]
        for point in path:
            dist_to_final = np.linalg.norm(final_destination - point)
            if dist_to_final < 10: pass 
            else:
                noise = random.uniform(0, 3)
                angle = random.uniform(0, 2 * np.pi)
                point[0] += np.cos(angle) * noise
                point[1] += np.sin(angle) * noise
        return path

    def _convert_path_to_actions(self, path):
        """Converts an array of (x,y) points to low-level move and pause actions."""
        if len(path) < 2: return
        
        total_dist = sum(np.linalg.norm(path[i] - path[i-1]) for i in range(1, len(path)))
        if total_dist == 0: return
        
        total_duration_s = total_dist / self.config['AVG_PIXELS_PER_SECOND']
        start_mult = self.config['START_SPEED_MULTIPLIER']
        end_mult = self.config['END_SPEED_MULTIPLIER']
        speed_multipliers = np.linspace(start_mult, end_mult, len(path))

        for i in range(1, len(path)):
            segment_dist = np.linalg.norm(path[i] - path[i-1])
            segment_duration = (segment_dist / total_dist) * total_duration_s
            adjusted_duration = segment_duration / speed_multipliers[i]
            
            target_x_int = round(path[i][0])
            target_y_int = round(path[i][1])
            dx = target_x_int - self.current_x
            dy = target_y_int - self.current_y

            if dx != 0 or dy != 0:
                self._add_action(('REL_MOVE', (dx, dy)))
                self.current_x += dx
                self.current_y += dy
            
            if adjusted_duration > 0:
                self._add_action(('PAUSE', adjusted_duration * random.uniform(0.8, 1.2)))

        # THE FIX: Add a final, small correction step to ensure we land perfectly.
        final_target_x = round(path[-1][0])
        final_target_y = round(path[-1][1])
        final_dx = final_target_x - self.current_x
        final_dy = final_target_y - self.current_y
        if final_dx != 0 or final_dy != 0:
            self._add_action(('REL_MOVE', (final_dx, final_dy)))
    
    def wake_up_screen(self):
        """Generates a small, quick mouse wiggle to wake the screen."""
        self.clear_plan() # Start with a clean plan
        # A quick move right and back left
        self._add_action(('REL_MOVE', (15, 0)))
        self._add_action(('PAUSE', 0.05))
        self._add_action(('REL_MOVE', (-15, 0)))
        self.current_x = 0 # Reset tracker
        self.current_y = 0
        return self
    def click(self, button='LEFT'):
        """Generates a click action."""
        self._add_action(('PAUSE', random.uniform(0.05, 0.2)))
        self._add_action(('MOUSE_BTN', (button.upper(), 'press')))
        self._add_action(('PAUSE', random.uniform(0.04, 0.08)))
        self._add_action(('MOUSE_BTN', (button.upper(), 'release')))
        return self
     
    def move_to(self, target_x, target_y):
        start_point = (self.current_x, self.current_y)
        end_point = (target_x, target_y)
        waypoints = self._generate_fractal_path(start_point, end_point, self.config['FRACTAL_DEPTH'])
        smooth_path = self._interpolate_waypoints(waypoints)
        final_path = self._add_precision_and_noise(smooth_path)
        self._convert_path_to_actions(final_path)
        return self
    
    def scroll(self, amount):
        """
        Appends scroll actions to the plan.
        Positive ticks = scroll up.
        Negative ticks = scroll down.
        """
        steps = abs(amount) // 5
        if steps == 0: steps = 1
        direction = 1 if amount > 0 else -1
        for _ in range(steps):
            # THE FIX: Ensure params is always a tuple by adding a comma
            self._add_action(('SCROLL', (direction,)))
            self._add_action(('PAUSE', random.uniform(0.01, 0.03)))
        return self

    def type_text(self, text):
        """Generates a sequence of key presses to type text."""
        for char in text:
            modifier = 0x00; keycode = 0x00
            
            if char in SHIFT_MAP:
                modifier = 0x02
                base_char = SHIFT_MAP[char]
                keycode = KEYCODE_MAP.get(base_char, 0x00)
            elif char.isupper():
                modifier = 0x02
                keycode = KEYCODE_MAP.get(char.lower(), 0x00)
            else:
                keycode = KEYCODE_MAP.get(char, 0x00)

            if keycode != 0x00:
                # THE FIX: Ensure params is always a tuple
                self._add_action(('KEY', (keycode, modifier, 'press')))
                self._add_action(('PAUSE', random.uniform(0.03, 0.09)))
                self._add_action(('KEY', (keycode, modifier, 'release')))
                self._add_action(('PAUSE', random.uniform(0.05, 0.15)))
        return self
    
    def generate_output(self, format='human', log_file=None):
        """Generates the final output and optionally saves a human-readable log."""
        
        # --- First, handle the plot format as it's a special case ---
        if format == 'plot':
            start_x, start_y = self.current_x, self.current_y
            if self.action_plan and self.action_plan[0][0] == 'REL_MOVE':
                start_x -= self.action_plan[0][1][0]
                start_y -= self.action_plan[0][1][1]
            
            x_coords = [start_x]; y_coords = [start_y]
            for action, params in self.action_plan:
                if action == 'REL_MOVE':
                    dx, dy = params
                    x_coords.append(x_coords[-1] + dx)
                    y_coords.append(y_coords[-1] + dy)
            
            plt.plot(x_coords, y_coords, marker='o', linestyle='-', markersize=1, lw=0.5)
            plt.title("Generated Mouse Path"); plt.xlabel("X Coordinate"); plt.ylabel("Y Coordinate")
            plt.gca().invert_yaxis(); plt.grid(True); plt.axis('equal'); plt.show()
            return ["Plot displayed."]

        # --- For all other formats, we build the output line-by-line in a single loop ---
        output_lines = []
        human_log = []
        pos_x, pos_y, total_sleep = self.current_x, self.current_y, 0.0

        # Determine the true start position for logging
        start_x, start_y = self.current_x, self.current_y
        if self.action_plan and self.action_plan[0][0] == 'REL_MOVE':
             start_x -= self.action_plan[0][1][0]
             start_y -= self.action_plan[0][1][1]
        human_log.append(f"Start Position: ({start_x}, {start_y})")

        for i, (action, params) in enumerate(self.action_plan):
            # Always build the human-readable log entry
            if action == 'REL_MOVE':
                dx, dy = params; pos_x += dx; pos_y += dy
                human_log.append(f"  - Step {i+1}: REL_MOVE by ({dx}, {dy}) -> New Pos: ({pos_x}, {pos_y})")
            elif action == 'PAUSE':
                duration = params; total_sleep += duration
                human_log.append(f"  - Step {i+1}: PAUSE for {duration:.4f}s (Total Sleep: {total_sleep:.2f}s)")
            elif action == 'MOUSE_BTN':
                human_log.append(f"  - Step {i+1}: MOUSE_BTN {params[0]} {params[1].upper()}")
            elif action == 'KEY':
                human_log.append(f"  - Step {i+1}: KEY {params[2].upper()} (code={params[0]}, mod={params[1]})")
            elif action == 'SCROLL':
                human_log.append(f"  - Step {i+1}: SCROLL by ({params[0]})")
            
            # Build the pi_command output if requested
            if format == 'pi_command':
                if action == 'REL_MOVE': output_lines.append(f"REL_MOVE|{params[0]}|{params[1]}")
                elif action == 'PAUSE': output_lines.append(f"PAUSE|{params}")
                elif action == 'MOUSE_BTN': output_lines.append(f"MOUSE|{params[0]}|{params[1]}")
                elif action == 'KEY': output_lines.append(f"KEY|{params[0]}|{params[1]}|{params[2]}")
                elif action == 'SCROLL': output_lines.append(f"SCROLL|{params[0]}")

        # --- Save the log to a file if requested ---
        if log_file:
            with open(log_file, 'w') as f:
                f.write(f"--- AUROCH Action Plan Log ---\n")
                f.write(f"Total Steps: {len(self.action_plan)}\n\n")
                f.write("\n".join(human_log))
            print(f"✅ Detailed log saved to {log_file}")

        # --- Return the correct output ---
        if format == 'human':
            return human_log
        else: # pi_command
            return output_lines

if __name__ == "__main__":

    # Use argparse for robust command-line argument handling
    parser = argparse.ArgumentParser(description="Generate human-like mouse movement plans.")
    parser.add_argument("format", choices=['human', 'pi_command', 'raw_hid', 'plot'], help="The output format for the plan.")
    parser.add_argument("target_x", type=int, help="The target X coordinate.")
    parser.add_argument("target_y", type=int, help="The target Y coordinate.")
    parser.add_argument("--save", dest="save_path", help="Path to save the generated action plan as a JSON file.")
    
    args = parser.parse_args()

    # Generate the plan
    h = Humanizer()
    h.move_to(args.target_x, args.target_y)
    
    # Save the plan to a file if requested
    if args.save_path:
        with open(args.save_path, 'w') as f:
            json.dump(h.action_plan, f)
        print(f"\n✅ Plan saved to {args.save_path}")

    # Generate and print the output
    print(f"\n--- Output Format: {args.format} ---")
    for line in h.generate_output(format=args.format):
        print(line)