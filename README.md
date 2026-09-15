# Sensor Recording Toolkit

Open source recording toolkit for Hesai Pandar 40P, Vectornav VN-200 and Zed2i Stereo camera


# Build and Run Commands
Build in the current working directory and source it. Alternatively, for individual module builds, if needed, navigate to each subdirectory (Hesai_ROS_2.0, zed_ros2, zed2i, vectornav, etc.), colcon build individually, and source the respective setup files.

Find Hesai_SDK build instructions in the upstream repo



Run the driver node (default behavior):

```bash
ros2 run driver driver_node
```

Run ZED only:

```bash
ros2 run driver driver_node -- zed
```

Run ZED with explicit output directory:

```bash
ros2 run driver driver_node -- zed /path/to/output_dir
```

Run VectorNav only (records `/vectornav/*` topics):

```bash
ros2 run driver driver_node -- vn
```

Run ZED + VectorNav:

```bash
ros2 run driver driver_node -- zed+vn
```

Run Hesai only:

```bash
ros2 run driver driver_node -- hesai
```

Run Hesai + VectorNav (single combined rosbag):

```bash
ros2 run driver driver_node -- hesai+vn
```

Run all sensors (ZED + Hesai + VectorNav):

```bash
ros2 run driver driver_node -- all
```

Show command help:

```bash
ros2 run driver driver_node -- -h
```

## Recording Output Location

- If you pass an output path, all outputs are stored there.
- If no output path is provided, data is stored under:
	- `~/ros2_bags/session_<timestamp>/`
- VectorNav-only rosbag path (`vn` or `zed+vn`):
	- `<output_dir>/rosbag_vectornav/rosbag_vectornav_0.db3.zstd`
- Hesai-only rosbag path (`hesai`) recording `/lidar_points`, `/lidar_imu`, `/lidar_packets`:
	- `<output_dir>/rosbag_lidar/rosbag_lidar_0.db3.zstd`
- Combined Hesai+VN rosbag path (`hesai+vn` or `all` when both are enabled) recording Hesai topics above + `/vectornav/*`:
	- `<output_dir>/rosbag_lidar+vn/rosbag_lidar+vn_0.db3.zstd`
- ZED SVO2 path:
	- `<output_dir>/zed_data.svo2`

Example:

```bash
ros2 run driver driver_node -- vn ~/.
```

This resolves to output directory `~` (your home folder), so the bag is in:

- `~/rosbag_vectornav/rosbag_vectornav_0.db3.zstd`

## Clock Sync Notes

- `Ptp_master.sh` is used to sync the LiDAR clock to the system clock.
- Future plan: extract the PPS signal from VectorNav and use it to discipline the system clock.
- Then use this sync flow to tune LiDAR and camera timing together.
- ZED2i syncs to sys clock internally based on zed2i documentation

## RViz2 Config
If needed, the RViz2 display configuration file is in the `zed2i` folder:

- `zed2i/dual_view.rviz`
