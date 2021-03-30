# d3dshot_screen_grabber


## Overview

This Python script implements a `rospy` ROS node which uses [d3dshot][] to make screenshots of a Windows desktop and publishes those both as [sensor_msgs/Image][]s as well as [sensor_msgs/CompressedImage][]s (JPEG compression).
[sensor_msgs/CameraInfo][] messages are also published.


## Supported OS and Python versions

As `d3dshot` only works on Windows, this node only works on Windows.

Only Windows 10 has been tested.

The authors have only used Python `3.8.x`.


## Installation

This is not a regular ROS package, as it is intended to be used with [rospypi/simple][], the pure Python, minimalistic package index for ROS 1 packages.
The index provides a convenient way to setup `venv`s for `rospy` and related packages, which greatly reduces the overhead of running ROS 1 on Windows.

Users are encouraged to create a `venv` and install all dependencies in that `venv` (update paths below as required):

```cmd
REM create the venv
python -m venv venv_d3dshot_screen_grabber

REM activate the venv
venv_d3dshot_screen_grabber\Scripts\activate.bat

REM update pip itself
pip install -U pip wheel
```

### Dependencies

By default, the node will install and use [opencv-python-headless][], which is a CPU only version of OpenCV.
If you already have OpenCV installed (important: the Python bindings are required), or will install another version of OpenCV in the `venv`, run the following command:

```cmd
pip install -r path\to\d3dshot_screen_grabber\requirements_no_cv.txt
```

If you do not have OpenCV installed and just want to use the default (ie: `opencv-python-headless`), run:

```cmd
pip install -r path\to\d3dshot_screen_grabber\requirements.txt
```

## General usage

To start the node, make sure a `roscore` is running (locally, or on remote PC) and:

```cmd
REM make sure the venv is active
venv_d3dshot_screen_grabber\Scripts\activate.bat

REM setup the environment
set ROS_IP=<ip of this PC>
set ROS_MASTER_URI=http://<ip of the PC running roscore>:11311

REM start the node
python path\to\d3dshot_screen_grabber\node.py WINDOW_NAME
```

Alternatively, specify the local IP and URI of the ROS master using command line arguments:

```cmd
python path\to\d3dshot_screen_grabber\node.py WINDOW_NAME __ip:=<ip of this PC> __master:=http://<ip of the PC running roscore>:11311
```

It may be convenient to create a `.bat` or `.cmd` to easily start the node with the required command line arguments (note: `^` is the line-continuation character):

```cmd
path\to\venv_d3dshot_screen_grabber\Scripts\python.exe ^
  path\to\d3dshot_screen_grabber\node.py ^
  __ip:=<ip of this PC> ^
  __master:=http://<ip of the PC running roscore>:11311 ^
  WINDOW_NAME
```

See `--help` for the usage specification and additional command line arguments.


## Example

This example shows how to capture the full window of the Calculator application and publish it on `/capture/calculator/image_rect_color` (the namespace is provided as a command line argument, the topic name is default in accordance with naming practices of ROS topics for cameras).

Follow the steps in the previous section to activate the `venv`, setup the environment and then:

```cmd
REM start the calculator
calc

REM start the node:
REM
REM   -f   : push the Calculator window to the foreground
REM   --ns : override the default namespace
python path\to\d3dshot_screen_grabber\node.py -f --ns="capture/calculator" "Calculator"
```

On the receiving side, start either an `image_view` node or RViz and subscribe to the `/capture/calculator/image_rect_color` topic.


[d3dshot]: https://pypi.org/project/d3dshot
[sensor_msgs/Image]: https://docs.ros.org/en/api/sensor_msgs/html/msg/Image.html
[sensor_msgs/CompressedImage]: https://docs.ros.org/en/api/sensor_msgs/html/msg/CompressedImage.html
[sensor_msgs/CameraInfo]: https://docs.ros.org/en/api/sensor_msgs/html/msg/CameraInfo.html
[rospypi/simple]: https://github.com/rospypi/simple
[opencv-python-headless]: https://pypi.org/project/opencv-python-headless
