#!/usr/bin/env python3

import sys
import signal
import time
import os
import argparse

try:
    import pyzed.sl as sl
except ImportError as e:
    print(f"[ERROR] Failed to import pyzed module: {e}")
    print(f"[ERROR] Current Python: {sys.executable}")
    print(f"[ERROR] Make sure ZED SDK Python API is installed in this Python environment")
    sys.exit(1)

# Global flags
is_recording = True

def signal_handler(sig, frame):
    global is_recording
    print("\n[INFO] Stop signal received. Finishing recording...")
    is_recording = False

def main():
    # 1. Parse output directory from launch file
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=str, required=True,
                        help='Directory to save the SVO2 file')
    args = parser.parse_args()

    session_path = args.output_dir
    os.makedirs(session_path, exist_ok=True)

    print(f"[INFO] Saving ZED data to: {session_path}")

    # ---------------------------------------------------------
    # Start ZED Recording (SVO2)
    # ---------------------------------------------------------
    print(f"[INFO] Initializing ZED Camera...")
    zed = sl.Camera()
    init = sl.InitParameters()
    init.camera_resolution = sl.RESOLUTION.HD720
    init.camera_fps = 60
    init.depth_mode = sl.DEPTH_MODE.NEURAL
    print(f"[DEBUG] Camera settings: 720p @ 60fps, depth_mode=NEURAL")

    print(f"[INFO] Opening ZED camera...")
    err = zed.open(init)
    if err != sl.ERROR_CODE.SUCCESS:
        print(f"[ERROR] ZED Open Failed: {err}")
        print(f"[ERROR] Make sure ZED camera is connected and no other process is using it")
        sys.exit(1)
    print(f"[SUCCESS] ZED camera opened successfully")

    svo_filename = os.path.join(session_path, "zed_data.svo2")
    print(f"[INFO] Setting up SVO recording to: {svo_filename}")
    rec_params = sl.RecordingParameters(svo_filename, sl.SVO_COMPRESSION_MODE.H264)

    print(f"[INFO] Enabling ZED recording...")
    err = zed.enable_recording(rec_params)
    if err != sl.ERROR_CODE.SUCCESS:
        print(f"[ERROR] ZED Recording Failed: {err}")
        print(f"[ERROR] Check disk space and write permissions for: {session_path}")
        zed.close()
        sys.exit(1)
    print(f"[SUCCESS] ZED recording enabled")

    # ---------------------------------------------------------
    # Recording Loop
    # ---------------------------------------------------------
    print(f"\n[SUCCESS] RECORDING ACTIVE")
    print(f"   --> SVO2: {os.path.basename(svo_filename)}")
    print("   (Press Ctrl+C to stop)\n")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    frames = 0
    start_t = time.time()
    last_file_check = time.time()

    while is_recording:
        grab_status = zed.grab()
        if grab_status == sl.ERROR_CODE.SUCCESS:
            frames += 1
            if frames % 60 == 0:
                duration = time.time() - start_t

                if time.time() - last_file_check > 5:
                    svo_size = os.path.getsize(svo_filename) / (1024*1024) if os.path.exists(svo_filename) else 0
                    sys.stdout.write(f"\r[REC] Duration: {duration:.1f}s | ZED Frames: {frames} | SVO Size: {svo_size:.1f}MB")
                    last_file_check = time.time()
                else:
                    sys.stdout.write(f"\r[REC] Duration: {duration:.1f}s | ZED Frames: {frames}")
                sys.stdout.flush()
        elif grab_status != sl.ERROR_CODE.SUCCESS:
            print(f"\n[ERROR] ZED grab failed: {grab_status}")
            break

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------
    print("\n\n[INFO] Stopping recording...")

    print("[INFO] Disabling ZED recording...")
    zed.disable_recording()
    print("[INFO] Closing ZED camera...")
    zed.close()

    # Show final file sizes
    print("\n[INFO] Recording Summary:")
    if os.path.exists(svo_filename):
        svo_size = os.path.getsize(svo_filename) / (1024*1024)
        print(f"   --> SVO2: {svo_size:.1f} MB")
    else:
        print(f"   --> SVO2: NOT CREATED!")

    print(f"\n[SUCCESS] Session Saved: {session_path}")

if __name__ == "__main__":
    main()