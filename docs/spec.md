# VM Orchestration

## VM Template

`vm_template.xml`

This file is the master hardware blueprint vms created by `auroch.sh`.

It defines consistent, stable, and minimal hardware, ensuring every cloned agent is identical and reliable.

The template specifies a modern 64-bit virtual machine with 2 vCPUs and 4GB of RAM. It uses Ubuntu 24.04.  It also leverages high-performance VirtIO drivers for both the disk and network interfaces, which provides significantly better throughput than older, emulated hardware.

The graphics and input configuration is VGA/VNC specifically for maximum compatibility and stability with the Raspberry Pi Zero 2 W after extensive testing. In other graphics configurations I am not able to see the mouse moving on the screen, which is really critical for debugging. Possibly in the future this is not so critically important. Another problem I have frequently encountered in development is the GUI stopping after a restart. This seems to be primarily related to not shutting down and properly 'flattening' the image before trying to promote and clone a VM. A virtual USB Tablet is also included, which is critical for ensuring the mouse cursor is always visible, the GUI always, appears, and the mouse behaves correctly within the VNC console.

### Design Choices
  - Intentional omission of hardcoded MAC address allows the system to generate unique one for every new clone 
  - Unnecessary hardware, such as sound cards removed to create the cleanest and most minimal virtual environment 
  - For maximum performance, `host-passthrough` CPU model is used which exposes the full feature set of the host CPU to the guest

The vm_template.xml is configured with a VirtIO-FS filesystem device, allowing a directory on the host to be shared directly with the VM. Inside the guest, an entry in the /etc/fstab file automatically mounts this shared device at /mnt/shared on boot. This creates a seamless and efficient bridge for transferring files, such as scripts or logs, between the host and the guest environment. Sometimes, when the system is shutdown, it is necessary to mount it again with `sudo mount -t virtiofs host_share /mnt/host_share`.

## Lifecycle Script `auroch.sh`

`sudo ./auroch.sh clone|start|stop|destroy|snapshot|revert|promote vm_name`

### `clone_vm()`
This function creates a new virtual machine by making a space-efficient copy of a parent image's disk and then using your `vm_template.xml` to define the new VM's hardware configuration. The clone function currently does not start a vm upon cloning, but it is possible I will add that as an option in the future.

### `start_vm()`
This is a simple wrapper for the `virsh start` command, which boots the specified virtual machine. 

### `stop_vm()`
This is a simple wrapper for the `virsh shutdown` command, which sends a graceful power-off signal to the virtual machine.

### `destroy_vm()`
This function completely and irreversibly deletes a VM by forcing it to power off, removing its configuration, and deleting its disk file.

### `snapshot_vm()`
This function saves a lightweight "checkpoint" of a running VM's memory and disk state using the `virsh snapshot-create-as` command, allowing you to return to that exact moment later.

### `revert_vm()`
This function restores a shut-down VM to a previously saved snapshot using the `virsh snapshot-revert` command.

### `promote_vm()`
This function updates the master golden image by taking a finalized clone, "flattening" its layered disk into a single file with `qemu-img convert`, and using it to replace the old golden image.

### A command to cleanly shutdown a vm before restarting
`sudo apt autoremove -y && sudo apt clean -y && sudo rm /etc/machine-id && sudo touch /etc/machine-id && sudo shutdown now`

`virsh list --all` is useful to check if any abandoned vms are running. And `virsh domblklist vm_name` will show where the storage is.

`systemctl status, start, stop` are useful at all points in this project - as long as you know what services should be running. 

## VM Setup Script

`setup.sh`

This script is the master "recipe" for configuring the software inside a fresh Ubuntu VM to turn it into our fully functional builder image, if for any reason the VM has to be abandoned. It is a version-controlled list of every command required for setup, including system updates, dependency installation, and the creation of necessary configuration files. It is not frequently actually used, but I try to do my best to keep it updated with everything important that has been done on the shell. For now, this is just to update & upgrade apt, then create and mount the shared folder, and then to create a python virtual environment and install packages.


## Screenshot and VM Side Communication

# Human-like Mouse and Typing

## Pi Configuration (hid.sh)

Configures our Raspberry Pi Zero W 2 to work as a composite HID device. This script uses the libcomposite kernel module to create a virtual USB device, mimicing a generic device. The script then creates mouse that sends 4 bytes, and a keyboard that sends 8. Finally, it links this function to a configuration and activates the entire gadget, making the Pi appear as a new, plug-and-play USB mouse to any connected computer.

Here are some commands for testing and cleanup - they are not really necessary, and I have found it preferable just to `sudo reboot` and then run the bash script again for setup. 

```bash
# Ensure the composite gadget support is loaded
sudo modprobe libcomposite
# Mount configfs if it's not already mounted
sudo mount -t configfs none /sys/kernel/config || true
# Inspect that configfs is present
ls -al /sys/kernel/config/usb_gadget
#if there is something in /sys/kerne/config/usb_gadget, the mount worked. so then you clean up safely:
G=/sys/kernel/config/usb_gadget/g1
if [ -d "$G" ]; then
  # Unbind if bound
  echo "" | sudo tee "$G/UDC" >/dev/null 2>&1 || true
  # Remove prior configuration/function state
  sudo rm -f "$G"/configs/c.1/* 2>/dev/null || true
  sudo rm -f "$G"/functions/hid.usb0 2>/dev/null || true
  sudo rmdir "$G"/configs/c.1 2>/dev/null || true
  sudo rmdir "$G" 2>/dev/null || true
fi
```

### Add executable, and run the script in such a way that it shows errors (-x)
```bash
sudo chmod +x hid.sh
sudo bash -x ./hid.sh
```

### To verify binding from the Pi, in case any issues
```bash
cat /sys/kernel/config/usb_gadget/g1/UDC   # should show a non-empty UDC name
ls /sys/class/udc                          # shows available controller like 20980000.usb
lsmod | grep dwc2

# should look like the below
agar@raspberrypi:~ $ cat /sys/kernel/config/usb_gadget/g1/UDC
3f980000.usb
agar@raspberrypi:~ $ ls /sys/class/udc
3f980000.usb
agar@raspberrypi:~ $ lsmod | grep dwc2
dwc2                  196608  0

ls -l /dev/hidg* # shows all hidg folders - should be 2 with script setting up keyboard and mouse
```

### How to verify from host
```bash
lsusb # show usb devices
sudo dmesg -w # watch for the correct logs
sudo evtest # look at details of what the device is sending
```

Removing and plugging back in the Pi should look like 

```bash 
[532527.301519] usb 3-1: USB disconnect, device number 66
[532528.924258] usb 3-1: new high-speed USB device number 67 using xhci_hcd
[532529.050605] usb 3-1: New USB device found, idVendor=046d, idProduct=c077, bcdDevice= 6.12
[532529.050611] usb 3-1: New USB device strings: Mfr=1, Product=2, SerialNumber=3
[532529.050615] usb 3-1: Product: USB Mouse
[532529.050617] usb 3-1: Manufacturer: Logitech
[532529.058664] input: Logitech USB Mouse as /devices/pci0000:00/0000:00:01.2/0000:02:00.0/0000:03:08.0/0000:07:00.3/usb3/3-1/3-1:1.0/0003:046D:C077.0049/input/input67
[532529.058823] hid-generic 0003:046D:C077.0049: input,hidraw7: USB HID v1.01 Mouse [Logitech USB Mouse] on usb-0000:07:00.3-1/input0
[532529.061043] input: Logitech USB Mouse as /devices/pci0000:00/0000:00:01.2/0000:02:00.0/0000:03:08.0/0000:07:00.3/usb3/3-1/3-1:1.1/0003:046D:C077.004A/input/input68
[532529.103320] hid-generic 0003:046D:C077.004A: input,hidraw8: USB HID v1.01 Keyboard [Logitech USB Mouse] on usb-0000:07:00.3-1/input1
```
To inspect usb traffic for further debugging:
```bash
sudo modprobe usbmon
lsusb
(take whichever BUS it is on )
sudo cat /sys/kernel/debug/usb/usbmon/{bus}u
```
And to see how the host interprets it:
```bash
xinput list
(get the id of your device)
xinput test <id>
```

### Setup Within VM

Go to Details in the View menu of QEMU, then click Add New Device, and select your device from the list.

`sudo evtest` should show two new devices that we just set up, even though you only have to add one device on the VM

### The Correct Device Mapping
* **Mouse:** `/dev/hidg0` (4-byte reports)
* **Keyboard:** `/dev/hidg1` (8-byte reports)

### Once the Pi is sending signals, you can test basic commands with the following:
```bash
# buttons=0, dx=5, dy=0 → small move right
printf '\x00\x05\x00' | sudo tee /dev/hidg0 >/dev/null
# buttons=0, dx=0, dy=5 → small move down
printf '\x00\x00\x05' | sudo tee /dev/hidg0 >/dev/null
# buttons=1, dx=0, dy=0 → left click down
printf '\x01\x00\x00' | sudo tee /dev/hidg0 >/dev/null
# buttons=0, dx=0, dy=0 → release
printf '\x00\x00\x00' | sudo tee /dev/hidg0 >/dev/null
# Example: move right 20, down 10
printf '\x00\x14\x0A' | sudo tee /dev/hidg0 >/dev/null

### **Mouse Movement (`/dev/hidg0`)**
# Move Down & Right:**
`printf '\x00\x14\x14\x00' | sudo tee /dev/hidg0`
# Move Down & Left:**
`printf '\x00\xEC\x14\x00' | sudo tee /dev/hidg0`
# Move Up & Right:**
`printf '\x00\x14\xEC\x00' | sudo tee /dev/hidg0`
# Move Up & Left:**
`printf '\x00\xEC\xEC\x00' | sudo tee /dev/hidg0`
# Move Down:**
`printf '\x00\x00\x14\x00' | sudo tee /dev/hidg0`
# Move Up:**
`printf '\x00\x00\xEC\x00' | sudo tee /dev/hidg0`
# Move Right:**
`printf '\x00\x14\x00\x00' | sudo tee /dev/hidg0`
# Move Left:**
`printf '\x00\xEC\x00\x00' | sudo tee /dev/hidg0`
### Mouse Clicks (`/dev/hidg0`)
# Left Click Down:
(printf '\x01\x00\x00\x00' | sudo tee /dev/hidg0) && sleep 0.1 && (printf '\x00\x00\x00\x00' | sudo tee /dev/hidg0)
# Right Click Down:
`printf '\x02\x00\x00\x00' | sudo tee /dev/hidg0`
# Release All Buttons:
`printf '\x00\x00\x00\x00' | sudo tee /dev/hidg0`
# Scrolling (`/dev/hidg0`)
# Scroll Down:
`printf '\x00\x00\x00\x01' | sudo tee /dev/hidg0`
# Scroll Up:
`printf '\x00\x00\x00\xFF' | sudo tee /dev/hidg0`
### **Typing  (`/dev/hidg1`)
# Type 'p' (Scancode `\x13`):
(printf '\x00\x00\x13\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1) && sleep 0.1 && (printf '\x00\x00\x00\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1)
# Type 'o' (Scancode `\x12`):
(printf '\x00\x00\x12\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1) && sleep 0.1 && (printf '\x00\x00\x00\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1)
# Type 't' (Scancode `\x17`):
(printf '\x00\x00\x17\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1) && sleep 0.1 && (printf '\x00\x00\x00\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1)
# 'Enter' is keycode 0x28
(printf '\x00\x00\x28\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1) && sleep 0.1 && (printf '\x00\x00\x00\x00\x00\x00\x00\x00' | sudo tee /dev/hidg1)
```

## VM to Host 

###  Host-to-Pi Communication

The Host-to-Pi communication bridge is a one-way command channel. Its purpose is to allow the Host Controller (the "brain") to send high-level action commands to the Raspberry Pi (the "hand"). The Raspberry Pi then translates these commands into low-level hardware events. This architecture separates the decision-making logic on the host from the physical action execution on the Pi, making the system modular and robust.

The bridge uses the **ZeroMQ (ZMQ)** networking library in a synchronous **Request-Reply (`REQ`/`REP`) pattern**. The host script acts as the `REQ` client, sending a command and waiting for a simple "OK" confirmation. The Pi script acts as the `REP` server, waiting for a command, executing it, and sending back the confirmation. The data is sent as simple, human-readable strings, with parameters separated by a pipe (`|`) delimiter.


###  Testing Steps

This test will verify the entire chain, from your host script sending a command to the event being received and processed inside the VM.

1.  **Start the VM and Passthrough the Pi**
      * Use your `auroch.sh` script to start a fresh test VM.
      * Open `virt-manager`, go to the VM's hardware details, and use "Add Hardware" to passthrough the "Logitech USB Receiver" device.
2.  **Monitor Events in the VM**
      * Open a terminal **inside the VM**.
      * Run `sudo evtest` and select the device for your **mouse** (e.g., "Logitech USB Receiver") to begin monitoring for raw hardware events.
3.  **Start the Server on the Pi**
      * SSH into your Raspberry Pi.
      * Activate the virtual environment: `source ~/mouse/bin/activate`
      * Run the server with `sudo` to grant it hardware access:
        ```bash
        sudo python3 hid_server.py
        ```
      * It will print "✅ Pi Raw HID Server is running. Waiting for commands..." and wait.
4.  **Send a Command from the Host**
      * Open a new terminal on your **host machine**.
      * Activate your host's virtual environment: `source ~/auroch/host_venv/bin/activate`
      * Run your test client script to send a raw "move right by 20" command:
        ```bash
        python3 test_raw_control.py "MOUSE|00140000"
        ```
<!-- end list -->

  * **Verification**: The moment you run the command on the host, you should see new event lines, specifically an `EV_REL` event for `REL_X` with a value of `20`, appear in the `evtest` window running inside your VM. You should also see the mouse cursor visibly twitch to the right.


## `handuz.py` Documentation

### **Purpose**
The `handuz.py` script is the **Humanization Engine** for the AUROCH project. Its primary purpose is to translate high-level, abstract goals (like "move the mouse to these coordinates") into a detailed, low-level sequence of actions that are statistically and behaviorally indistinguishable from a real human. It is the core component responsible for the agent's stealth and realism.

### **The `Humanizer` Class**
This is the only class in the script. It is a stateful object that builds and manages a plan of actions.

* **Initialization and Configuration**
    The class is initialized with optional screen dimensions (`Humanizer(screen_width=1280, screen_height=800)`). All of the agent's "personality" and behavioral parameters are exposed in a single `self.config` dictionary at the top of the `__init__` method. This allows for easy tuning of key parameters like:
    - `AVG_PIXELS_PER_SECOND`: Controls the overall speed of mouse movements.
    - `START_SPEED_MULTIPLIER` / `END_SPEED_MULTIPLIER`: Creates the "zeroing in" effect by making movements faster at the start and slower at the end.
    - `FRACTAL_DEPTH`: Controls the complexity and randomness of the mouse path.
    - `PATH_STRATEGY_WEIGHTS`: Controls the likelihood of the mouse taking a direct path, overshooting, or taking a "scenic route."
* **Internal Methods**
  * **`_add_action(action_tuple)`**
This is a simple utility method that takes a low-level action tuple (e.g., `('REL_MOVE', (1,2))`) and appends it to the class's internal `action_plan` list, which is the sequence of steps to be executed.
  * **`_get_detour_distance(segment_length)`**
This function calculates how far a detour should deviate from the main path. It uses a **log-normal distribution** to ensure most detours are small while some are occasionally large. The distance is proportional to the length of the current movement segment, meaning longer moves have the potential for larger, more noticeable detours.
  * **`_generate_fractal_path(start, end, depth)`**
This is the core of the path generation. It's a **recursive** function that takes a straight line between two points and subdivides it, adding one or more random, semi-circular detours. It then calls itself on the new, smaller line segments. This process repeats, creating a noisy, complex, and unpredictable path that is different every time.
  * **`_interpolate_waypoints(waypoints)`**
After the fractal waypoints are generated, this function "connects the dots." It creates a smooth, high-resolution path by generating many small, straight-line points (**linear interpolation**) between each of the major waypoints from the fractal path.
  * **`_add_precision_and_noise(path)`**
This method adds the final layer of realism. It injects small, random noise into each point on the smooth path to simulate the natural tremor of a human hand. It reduces this noise to zero as the cursor gets within 10 pixels of its final destination, creating a "homing in" effect.
  * **`_convert_path_to_actions(path)`**
This is the final translation step. It takes the final, high-resolution path of absolute coordinates and converts it into the sequence of low-level `REL_MOVE` and `PAUSE` actions. It calculates the relative `(dx, dy)` for each step and determines the correct pause duration between each step based on the `AVG_PIXELS_PER_SECOND` configuration to control the overall speed.

* **Public Methods (API)**
    The `Humanizer` class is controlled via a set of simple, chainable methods:
    * `move_to(x, y)`: Generates a complete, human-like mouse movement from the cursor's last known position to the absolute target `(x, y)`.
    * `click(button)`: Generates a mouse button press and release, with randomized pauses.
    * `type_text(text)`: Generates a sequence of key presses and releases to type a string, complete with human-like cadence and a chance of simulated typos.
    * `scroll(amount)`: Generates a series of scroll wheel "tick" events.
    * `wake_up_screen()`: Generates a small, quick mouse wiggle, used to ensure the VM's screen is active before a sequence begins.
    * `clear_plan()`: Empties the internal action plan to start a new sequence, while preserving the cursor's last known position.

* **Output Generation**
    The `generate_output()` method is used to format the internally generated action plan for different consumers. It takes a `format` argument:
    * `human`: Produces a detailed, step-by-step log of every low-level move and pause, including cumulative time and distance.
    * `pi_command`: Produces a simple, delimited string format designed to be sent over the network to the `hid_server.py` on the Pi.
    * `plot`: Uses `matplotlib` to generate a 2D graph that visually displays the exact path the mouse will take.
    * It also takes an optional `log_file` argument to save the human-readable output directly to a file.

#### **Standalone Usage**
The script can be run directly from the command line for testing and debugging purposes. It accepts the output format and target coordinates as arguments.

* **Usage:** `python3 handuz.py <format> <x> <y> [--save <file>]`
* **Example:** `python3 handuz.py plot 800 600 --save my_plan.json` will display a plot of the generated path to (800, 600) and save the underlying action plan to `my_plan.json`.

### **The Reflex System** - TODO
This is a separate mode of operation to handle tasks like scrolling that require coordination between action and observation.

When the Host Controller decides to scroll, it will enter a "reflex" state. It will send a `SCROLL` command to the Pi as usual. Simultaneously, it will send a special `MONITOR_FOR_STABILITY` command to the **VM Agent**. The VM Agent will pause its normal screenshot loop and enter a high-frequency local loop where it captures the screen but does not send it. It will wait until the screen content stops changing for a set duration (e.g., 500ms), which indicates the scroll is complete. Only then will it send the single, final screenshot back to the Host Controller, signaling that the system can proceed to the next "Think" step. This same reflex mechanism can be used for any action that involves waiting for a visual change, like a loading spinner.

## `run_full_test.py` Documentation

### **Purpose**

This script serves as a comprehensive, end-to-end integration test for the core AUROCH system. It verifies that the `handuz.py` engine, the Host-to-Pi communication bridge, and the Raspberry Pi's hardware emulation are all working together correctly to perform a complex sequence of actions.

### **Functionality**

The script executes a hardcoded sequence of human-like actions. For each step in the sequence, it uses the `Humanizer` class to generate a detailed plan of low-level mouse and keyboard events. It then serializes this plan and sends it as a single message to the `hid_server.py` running on the Raspberry Pi for execution. The sequence includes waking the screen, pausing, multiple mouse movements, clicking, typing, and scrolling.

### **Configuration**

Before running, you must set the `PI_IP_ADDRESS` variable at the top of the script to the correct IP address of your Raspberry Pi on the network.

### **Usage**

To run the test, first ensure a configured VM is running with the Pi passed through to it, and that the `hid_server.py` is running on the Pi. Then, execute the script from your `~/auroch` directory:

```bash
python3 tests/run_full_test.py
```

#### **Output**

  * **Console:** The script will print the status of each high-level step as it is generated and sent.
  * **VM Actions:** You will see the mouse move, click, type, and scroll inside the live VM view, following the predefined sequence.
  * **Log Files:** For each step, a new `log_stepX_....txt` file is created in the project directory. Each file contains a detailed, human-readable breakdown of every tiny movement and pause that was generated for that specific action.

# Host Controller

## Host to Pi Communication

The Host-to-Pi communication bridge is a one-way command channel. Its purpose is to allow the Host Controller (the "brain") to send high-level action commands to the Raspberry Pi (the "hand"). The Raspberry Pi then translates these commands into low-level hardware events. This architecture separates the decision-making logic on the host from the physical action execution on the Pi, making the system modular and robust.

The bridge uses the **ZeroMQ (ZMQ)** networking library in a synchronous **Request-Reply (`REQ`/`REP`) pattern**. The host script acts as the `REQ` client, sending a command and waiting for a simple "OK" confirmation. The Pi script acts as the `REP` server, waiting for a command, executing it, and sending back the confirmation. The data is sent as simple, human-readable strings, with parameters separated by a pipe (`|`) delimiter.

-----



## `hid_server.py`

Due to issues with loading the correct python on the Pi, I have discovered it works to run `sudo /home/agar/mouse/bin/python3 hid_server.py`

  * **Purpose:** This script runs on the Raspberry Pi and acts as the physical "hand" of the agent. Its sole purpose is to receive a complete action plan from the Host Controller and then execute each step in the plan by sending the corresponding raw hardware events to the virtual USB mouse and keyboard devices.

  * **Functionality:** The script initializes a ZeroMQ `REP` (Reply) socket and waits for a connection. Upon receiving a JSON string containing a full action plan, it immediately sends a "PLAN\_RECEIVED" reply to the host to confirm receipt. It then begins executing the plan step-by-step, translating each action (e.g., `REL_MOVE`, `KEY`, `PAUSE`) into the appropriate 4-byte mouse or 8-byte keyboard HID report.

  * **Dependencies:** Requires `pyzmq` to be installed in its Python environment. It must be run with `sudo` to have permission to write to the `/dev/hidg*` device files. It depends on a correctly configured composite USB Gadget created by `hid.sh`.

  * **Input:** A single JSON string representing a list of action tuples, e.g., `[["REL_MOVE", [10, 10]], ["PAUSE", 0.05]]`.

  * **Output:**

      * **Hardware:** Raw USB HID reports written to the device files (`/dev/hidg0` for the mouse, `/dev/hidg1` for the keyboard).
      * **Console Log:** A verbose, real-time log of the plan execution.

-----

#### **Example Log Trace**

If the server receives a simple plan to move the mouse and then press the 'a' key, the console output on the Pi will look like this:

```
✅ Pi Executor is running. Waiting for a plan...

1. Received action plan.
2. Executing 4 steps...
➡️  Step 1: Action = REL_MOVE, Params = [10, 10]
  ↪️ Relative Move: dx=10, dy=10
🖱  Sending Mouse Report → Move: dx=10, dy=10
  ↳ Raw HID Bytes: 000a0a00
  ✔ Sent to /dev/hidg0

➡️  Step 2: Action = PAUSE, Params = 0.1
  ⏸ Pausing for 0.10 seconds...
➡️  Step 3: Action = KEY, Params = [4, 0, 'press']
  ⌨️  Key 4 with modifier 0 [press]
⌨️  Sending Keyboard Report → Keycode: 4
  ↳ Raw HID Bytes: 0000040000000000
  ✔ Sent to /dev/hidg1

➡️  Step 4: Action = KEY, Params = [4, 0, 'release']
  ⌨️  Key 4 with modifier 0 [release]
⌨️  Sending Keyboard Report → None (release)
  ↳ Raw HID Bytes: 0000000000000000
  ✔ Sent to /dev/hidg1

✅ All actions executed.

--> Plan execution complete.
```

## VM to Host Communication 

* Enables manual screenshot capture from a Wayland VM.
* Captured image is serialized using Protobuf and sent over TCP to the host.
* Host receives and saves the image file.
* Triggered manually by running a Python script inside a virtual environment on the VM.

Depends on:
* `protobuf` (Python module)
* `gnome-screenshot` (for Wayland)
* `protoc` (for `.proto` compilation)
* Python 3.6+

###  **How It Works**

#### On the **VM**:

* `gnome-screenshot` captures the screen to `/tmp/screen.png`.
* Python script reads image as bytes, packs it into a Protobuf `Screenshot` message:
    * `filename`: `"screen.png"`
    * `image_data`: PNG bytes
    * `timestamp`: Unix time in ms
    * Sends the message to the host via a TCP socket.

#### On the **Host**:
A Python server listens for incoming screenshot messages, and when a message is received:
  * Reads 4-byte length header, then full Protobuf message.
  * Parses and writes the image bytes to `recv_screen.png`.

```bash
# ON HOST
python host_recv_screenshot.py
# ON VM
python vm_send_screenshot.py
# Screenshot appears as `recv_screen.png` on the host.
```

### `screenshot.proto`

Defines the schema used to serialize screenshots:

```proto
message Screenshot {
  string filename = 1;
  bytes image_data = 2;
  int64 timestamp = 3;
}
```

### `vm_send_screenshot.py`

* Runs on the VM.
* Captures and sends the screenshot.

### `host_recv_screenshot.py`

* Runs on the host.
* Receives and saves the screenshot.

### `screenshot_pb2.py`

* Auto-generated from `.proto`.
* Used by both sender and receiver.


# Host UI

## Live Screenshot Display

## Graphical Annotation Tools

## Action Queue

## Data Logging

# AI Training

## Data Loading

## Preprocessing

## VLM Fine Tuning

## AI Integration

## Inference Engine

## Human-in-the-Loop

# Cloud Gateway

## Cloud Server Provisioning

## VPN Configuration??

## More network security

