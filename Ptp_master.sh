#!/bin/bash

# Function to detect the first active Ethernet interface
get_ethernet_interface() {
    # 1. List interfaces in /sys/class/net
    # 2. Exclude 'lo' (loopback) and 'wl*' (wireless)
    # 3. Check which one has a carrier (cable plugged in)
    
    for iface in /sys/class/net/*; do
        iface_name=$(basename "$iface")
        
        # Skip Loopback and Wireless
        if [[ "$iface_name" == "lo" ]] || [[ "$iface_name" == wl* ]]; then
            continue
        fi

        # Check if interface is physically connected (carrier == 1)
        # Some virtual interfaces might not have this file, suppress errors
        if grep -q "1" "$iface/carrier" 2>/dev/null; then
            echo "$iface_name"
            return 0
        fi
    done

    # Fallback: If no cable is plugged in, just pick the first non-wireless/loopback found
    # (Useful if you are setting up before plugging in)
    ip -o link show | awk -F': ' '{print $2}' | grep -E '^(en|eth)' | head -n 1
}

# ================= MAIN LOGIC =================

# 1. Auto-detect Interface
INTERFACE=$(get_ethernet_interface)

if [ -z "$INTERFACE" ]; then
    echo "[ERROR] Could not detect any Ethernet interface."
    echo "        Please check if your drivers are installed or the cable is plugged in."
    exit 1
fi

sudo apt install ptpd
echo "Making sure ptpd is installed..."
echo "[INFO] Detected Active Ethernet Interface: $INTERFACE"
echo "[INFO] Starting PTP Master configuration..."

# 2. Check for root
if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Please run as root: sudo ./auto_ptp_master.sh"
  exit 1
fi

# 3. Stop conflicting services
echo "[INFO] Stopping system time services..."
systemctl stop systemd-timesyncd
systemctl stop chrony 2>/dev/null

# 4. Sync System Time (Best Effort)
if ping -c 1 8.8.8.8 &> /dev/null; then
    echo "[INFO] Internet detected. Syncing to global NTP..."
    ntpdate -u pool.ntp.org 2>/dev/null
else
    echo "[WARNING] No internet. Using current system time."
fi

# 5. Set Hardware Clock
hwclock --systohc --utc

# 6. Start PTPd on the DETECTED interface
echo "[INFO] Killing old PTPd instances..."
killall ptpd 2>/dev/null

echo "[INFO] Starting PTPd Master on $INTERFACE..."
# -C runs in console (foreground) so you can see the output immediately
ptpd -M -i "$INTERFACE" -C