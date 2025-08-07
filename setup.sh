# 1. Update all system packages
sudo apt update && sudo apt upgrade -y

# 2. Create the directory where the shared folder will appear
sudo mkdir -p /mnt/shared

# 3. Add the share to the filesystem table to mount it automatically on boot
# The 'nofail' option is important; it prevents the VM from halting if the share isn't ready.
echo 'host_share /mnt/shared virtiofs defaults,nofail 0 0' | sudo tee -a /etc/fstab

# 4. reload daemon to mount
systemctl daemon-reload

# 5. Mount all filesystems in the table now, including the new one
sudo mount -a

# Alternatively, I used
# sudo mkdir -p /mnt/host_share
# sudo mount -t virtiofs host_share /mnt/host_share

sudo apt install python3-venv -y

python3 -m venv vm

source vm/bin/activate

pip install protobuf

