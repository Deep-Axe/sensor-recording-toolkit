#!/usr/bin/env python3

import os
import time
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node


class Zed2iNode(Node):
    def __init__(self) -> None:
        super().__init__("zed2i_node")

        self.declare_parameter("output_dir", "")

        output_dir_param = self.get_parameter("output_dir").get_parameter_value().string_value
        self.session_path = self._resolve_output_dir(output_dir_param)
        self.svo_path = str(self.session_path / "zed_data.svo2")

        self.get_logger().info(f"Saving ZED data to: {self.session_path}")

        try:
            import pyzed.sl as sl
        except ImportError as exc:
            self.get_logger().error(f"Failed to import pyzed.sl: {exc}")
            raise RuntimeError("pyzed.sl is required for zed2i_node") from exc

        self.sl = sl
        self.zed = self.sl.Camera()
        self.frames = 0
        self.start_time = time.time()
        self.last_log_t = self.start_time

        init = self.sl.InitParameters()
        init.camera_resolution = self.sl.RESOLUTION.HD720
        init.camera_fps = 60
        init.depth_mode = self.sl.DEPTH_MODE.NEURAL

        err = self.zed.open(init)
        if err != self.sl.ERROR_CODE.SUCCESS:
            raise RuntimeError(f"ZED open failed: {err}")

        rec_params = self.sl.RecordingParameters(self.svo_path, self.sl.SVO_COMPRESSION_MODE.H264)
        err = self.zed.enable_recording(rec_params)
        if err != self.sl.ERROR_CODE.SUCCESS:
            self.zed.close()
            raise RuntimeError(f"ZED recording setup failed: {err}")

        self.get_logger().info("ZED recording started. Press Ctrl+C to stop.")
        self._timer = self.create_timer(0.001, self._grab_once)

    def _resolve_output_dir(self, output_dir_param: str) -> Path:
        if output_dir_param:
            path = Path(os.path.expanduser(output_dir_param)).resolve()
            path.mkdir(parents=True, exist_ok=True)
            return path

        base = Path(os.path.expanduser("~/ros2_bags")).resolve()
        base.mkdir(parents=True, exist_ok=True)
        session = base / datetime.now().strftime("session_%Y%m%d_%H%M%S")
        session.mkdir(parents=True, exist_ok=True)
        return session

    def _grab_once(self) -> None:
        status = self.zed.grab()
        if status != self.sl.ERROR_CODE.SUCCESS:
            self.get_logger().error(f"ZED grab failed: {status}")
            self.destroy_node()
            return

        self.frames += 1
        now = time.time()
        if now - self.last_log_t >= 2.0:
            size_mb = 0.0
            if os.path.exists(self.svo_path):
                size_mb = os.path.getsize(self.svo_path) / (1024.0 * 1024.0)
            self.get_logger().info(
                f"REC duration={now - self.start_time:.1f}s frames={self.frames} svo={size_mb:.1f}MB"
            )
            self.last_log_t = now

    def stop(self) -> None:
        if hasattr(self, "_timer"):
            self._timer.cancel()

        if hasattr(self, "zed"):
            try:
                self.zed.disable_recording()
            except Exception:
                pass
            try:
                self.zed.close()
            except Exception:
                pass

        if os.path.exists(self.svo_path):
            size_mb = os.path.getsize(self.svo_path) / (1024.0 * 1024.0)
            if rclpy.ok():
                self.get_logger().info(f"Saved SVO2: {self.svo_path} ({size_mb:.1f} MB)")
            else:
                print(f"Saved SVO2: {self.svo_path} ({size_mb:.1f} MB)")
        else:
            if rclpy.ok():
                self.get_logger().warning(f"SVO2 file was not created: {self.svo_path}")
            else:
                print(f"SVO2 file was not created: {self.svo_path}")


def main() -> None:
    rclpy.init()
    node = None
    try:
        node = Zed2iNode()
        rclpy.spin(node)
    except RuntimeError as exc:
        if node is not None:
            node.get_logger().error(str(exc))
        else:
            print(exc)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.stop()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
