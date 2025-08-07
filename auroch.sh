#!/bin/bash
set -e # Exit immediately if a command fails

# --- Configuration ---
VM_STORAGE_ROOT="$HOME/vm_storage"
GOLDEN_IMAGE_PATH="$VM_STORAGE_ROOT/base_images/base_ubuntu_lts.qcow2"
BASE_IMAGE_PATH="$VM_STORAGE_ROOT/base_images/base_ubuntu_lts.qcow2"
VM_DISK_DIR="$VM_STORAGE_ROOT/disks"
VM_TEMPLATE_PATH="$(pwd)/vm_template.xml"

# Create all required directories
mkdir -p "$VM_DISK_DIR" "$(dirname "$GOLDEN_IMAGE_PATH")" "$(dirname "$BASE_IMAGE_PATH")"

usage() {
    echo "Usage: $0 {clone|start|stop|destroy|promote|snapshot|revert} vm_name [args]"
    echo "Commands:"
    echo "  clone <new_name> [source_name]  - Clones a VM. Defaults to the golden image."
    echo "  start <name>                   - Starts a VM."
    echo "  stop <name>                    - Stops a VM."
    echo "  destroy <name>                 - Destroys a VM."
    echo "  promote <name>                 - Promotes a VM to the golden image."
    echo "  snapshot <name> <snap_name>    - Creates a snapshot of a VM."
    echo "  revert <name> <snap_name>      - Reverts a VM to a snapshot."
    exit 1
}
# --- Main Functions ---
clone_vm() {
    local NEW_VM_NAME="$1"
    local SOURCE_VM_NAME="$2" # Optional: the name of the VM to clone from for branching
    echo "--> Creating new VM '$NEW_VM_NAME'..."

    local BACKING_FILE
    if [ -z "$SOURCE_VM_NAME" ]; then
        BACKING_FILE="$GOLDEN_IMAGE_PATH"
        echo "--> Based on the main golden image."
    else
        BACKING_FILE=$(virsh domblklist --inactive "$SOURCE_VM_NAME" || true | tail -n 1 | awk '{print $2}')
        echo "--> Branching from existing VM '$SOURCE_VM_NAME'."
        if [ ! -f "$BACKING_FILE" ]; then echo "Error: Source disk for '$SOURCE_VM_NAME' not found."; exit 1; fi
    fi

    local NEW_VM_DISK_PATH="$VM_DISK_DIR/$NEW_VM_NAME.qcow2"
    [ -f "$NEW_VM_DISK_PATH" ] && { echo "Error: Disk for '$NEW_VM_NAME' already exists"; exit 1; }

    qemu-img create -f qcow2 -F qcow2 -b "$BACKING_FILE" "$NEW_VM_DISK_PATH"
    
    XML_TEMP_FILE=$(mktemp)
    sed -e "s|VM_NAME_PLACEHOLDER|$NEW_VM_NAME|g" -e "s|VM_DISK_PATH_PLACEHOLDER|$NEW_VM_DISK_PATH|g" "$VM_TEMPLATE_PATH" > "$XML_TEMP_FILE"
    virsh define "$XML_TEMP_FILE"
    rm "$XML_TEMP_FILE"
    echo "VM '$NEW_VM_NAME' created successfully."
}

promote_vm() {
    local SOURCE_VM="$1"
    echo "=== Promoting $SOURCE_VM to become the new golden image ==="
    
    virsh shutdown "$SOURCE_VM" 2>/dev/null || true
    echo "Waiting for $SOURCE_VM to shut down..."
    while virsh list --state-running --name | grep -q "^$SOURCE_VM$"; do sleep 1; done
    
    local SOURCE_DISK=$(virsh domblklist --inactive "$SOURCE_VM" || true | tail -n 1 | awk '{print $2}')
    [ -z "$SOURCE_DISK" ] && { echo "Error: Could not find disk path for $SOURCE_VM."; exit 1; }
    
    echo "--> Converting image..."
    sudo qemu-img convert -O qcow2 "$SOURCE_DISK" "$GOLDEN_IMAGE_PATH.NEW"
    
    echo "--> Replacing old golden image..."
    sudo mv -f "$GOLDEN_IMAGE_PATH.NEW" "$GOLDEN_IMAGE_PATH"
    echo "Promotion complete."
}

snapshot_vm() {
    local VM_NAME="$1"
    local SNAP_NAME="$2"
    [ -z "$SNAP_NAME" ] && { echo "Error: Snapshot name required."; exit 1; }
    echo "--> Creating snapshot '$SNAP_NAME' for VM '$VM_NAME'..."
    virsh snapshot-create-as --domain "$VM_NAME" --name "$SNAP_NAME"
    echo "Snapshot created."
}

revert_vm() {
    local VM_NAME="$1"
    local SNAP_NAME="$2"
    [ -z "$SNAP_NAME" ] && { echo "Error: Snapshot name required."; exit 1; }
    echo "--> Reverting VM '$VM_NAME' to snapshot '$SNAP_NAME'..."
    virsh snapshot-revert --domain "$VM_NAME" --snapshotname "$SNAP_NAME"
    echo "Revert complete. Please start the VM."
}

destroy_vm() {
    echo "--> DESTROYING VM '$VM_NAME' (irreversible!)"
    read -p "Are you sure? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        virsh destroy "$VM_NAME" 2>/dev/null || true
        virsh undefine "$VM_NAME" --nvram 2>/dev/null || true
        rm -f "$VM_DISK_DIR/$VM_NAME.qcow2"
        rm -f "$VM_CONFIG_DIR/$VM_NAME.xml"
        echo "VM '$VM_NAME' permanently destroyed."
    else
        echo "Operation cancelled."
    fi
}

# --- Main Logic ---
COMMAND=$1
VM_NAME=$2
ARG3=$3

case "$COMMAND" in
    clone)      clone_vm "$VM_NAME" "$ARG3" ;;
    start)      virsh start "$VM_NAME" ;;
    stop)       virsh shutdown "$VM_NAME" ;;
    destroy)    destroy_vm "$VM_NAME" ;;
    promote)    promote_vm "$VM_NAME" ;;
    snapshot)   snapshot_vm "$VM_NAME" "$ARG3" ;;
    revert)     revert_vm "$VM_NAME" "$ARG3" ;;
    *)          usage ;;
esac