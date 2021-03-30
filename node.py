# Copyright (c) 2021, TU Delft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# author: Ting-Chia Chiang
# author: G.A. vd. Hoorn

import argparse
import ctypes
try:
    import cv2
except:
    print("Couldn't load cv2, is OpenCV installed?")
import sys
import time

try:
    import d3dshot
except:
    print("Couldn't load d3dshot, is it installed?")

import rospy
import rosgraph

from sensor_msgs.msg import CameraInfo
from sensor_msgs.msg import CompressedImage
from sensor_msgs.msg import Image

from cv_bridge import CvBridge


class NoSuchWindowException(Exception):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--rate', type=int, metavar='FPS',
        help="Rate at which to publish captured images", default=30)
    parser.add_argument('-n', '--namespace', type=str, metavar='NS',
        help="Namespace to publish images in", default='capture')
    parser.add_argument('--no-raw', action='store_true',
        help="Disable image_raw publisher")
    parser.add_argument('--no-compressed', action='store_true',
        help="Disable compressed publisher")
    parser.add_argument('-f', '--raise-to-front', action='store_true',
        help="When capturing a window: raise window to the front")
    parser.add_argument('--region', nargs=4, type=int,
        help="Region to capture relative to the extents of the window (x y w h). "
        "To capture a 640*480 region offset by 360 from the left of captured "
        "window and 193 from the top of the captured window, the arguments would "
        "be \"360 193 640 480\"")
    parser.add_argument('window', metavar='WINDOW', type=str,
        help="Title of window to capture")

    # Use rospy.myargv(..) to remove ROS remaps before passing argv to argparse, and then
    # pass remaining args to argparse, except the first element (name of the script).
    # This makes it possible to use ROS remapping arguments (such as '__name' and
    # '__master') without upsetting argparse.
    args = parser.parse_args(args=rospy.myargv(argv=sys.argv)[1:])

    try:
        # find the window with the name specified by the user
        print(f"Searching for window '{args.window}' ..")
        # TODO: consider using https://github.com/asweigart/PyGetWindow
        # TODO: or https://pypi.org/project/screeninfo
        extents = list(get_window_extents_by_title(args.window, exclude_titlebar=True))

        E_LEFT=0; E_TOP=1; E_RIGHT=2; E_BOTTOM=3
        img_width = extents[E_RIGHT] - extents[E_LEFT]
        img_height = extents[E_BOTTOM] - extents[E_TOP]
        print(f"Window extents: {extents}, dims: {img_width}x{img_height}")

        if args.region:
            # modify window extents based on region specified by user
            extents[E_LEFT] += args.region[E_LEFT]
            extents[E_TOP] += args.region[E_TOP]
            extents[E_RIGHT] = extents[E_LEFT] + args.region[2]
            extents[E_BOTTOM] = extents[E_TOP] + args.region[3]

            img_width = extents[E_RIGHT] - extents[E_LEFT]
            img_height = extents[E_BOTTOM] - extents[E_TOP]
            print(f"Updated extents: {extents}, dims: {img_width}x{img_height}")

        if args.raise_to_front:
            print(f"Will try to push window '{args.window}' to the front ..")
            bring_window_to_front(args.window)

    except NoSuchWindowException as e:
        sys.stderr.write(f"Couldn't find window '{args.window}, aborting'\n")
        sys.exit(1)

    # get d3dshot instance
    # note: we pass the 'args.rate' arg as fps here, as we need d3dshot to
    # capture at at least that rate to be able to achieve the requested
    # publication rate
    # TODO: move this to ctor of D3DShotPublisher, to avoid creating the instance
    # but then not destroying it if we don't get to pass it to D3DShotPublisher
    # below
    dshot = setup_d3dshot(fps=args.rate, region=extents)

    # wait a bit to give d3dshot time to fill the queue
    print("Warming up d3dshot queue ..")
    time.sleep(1)

    print("ROS settings:\n"
        f"  Node name: '{rospy.get_name()}'\n"
        f"  Local IP: {rosgraph.network.get_local_address()}\n"
        f"  ROS Master: {rosgraph.get_master_uri()}"
    )

    # init ROS
    # note: we do this here to avoid polluting the master with all sorts of ghost
    # nodes when d3dshot errors-out during initialisation and we can't properly
    # clean up after ourselves.
    # At this point we can be reasonably certain d3dshot will work
    rospy.init_node('d3dshot_publisher')

    # TODO: could perhaps wrap the ROS side in a try-except to handle the
    # tcpros exceptions thrown on SIGINT

    print(f"Starting {args.rate} Hz publisher(s) for\n"
        f"  display: {dshot.display.name}\n"
        f"  adapter: {dshot.display.adapter_name}\n"
        f"  resolution: {dshot.display.resolution[0]}x{dshot.display.resolution[1]}"
    )
    # start publishing frames as ROS messages
    with setup_d3dshot_pub(dshot, args, img_width, img_height) as shot_pub:
        # exit from this context will also take down the d3dshot instance
        shot_pub.spin()


def setup_d3dshot_pub(dshot, args, img_width, img_height):
    # Note: width and height may be different from dshot.display properties
    return D3DShotPublisher(dshot, img_width, img_height, ns=args.namespace,
        pub_raw=not args.no_raw, pub_compressed=not args.no_compressed,
        rate=args.rate)


# TODO: move this to D3DShotPublisher ctor to make it responsible for setup and teardown
def setup_d3dshot(display_id=0, fps=30, region=None):
    # Captures will be np.ndarray of dtype uint8 with values in range (0, 255)
    dshot = d3dshot.create(capture_output="numpy")
    dshot.display = dshot.displays[display_id]
    # start 'high-speed' capture
    # note: we do this to decouple capture of the screen from the ROS event
    # and processing loop. Captures will be read from the d3dshot queue
    if not dshot.capture(target_fps=fps, region=region):
        raise ValueError(f"Failed to start d3dshot capture (unknown reason)")
    return dshot


def bring_window_to_front(window_title):
    # TODO: probably doesn't work for everything
    # TODO: check whether this is OK for ctypes, or we need to be stricter
    # with typing
    hwnd = ctypes.windll.user32.FindWindowW(0, window_title)
    if not hwnd:
        raise NoSuchWindowException(f"Can't find window '{window_title}'")
    if ctypes.windll.user32.IsIconic(hwnd):
        SW_RESTORE: int = 9
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.1)
    ctypes.windll.user32.BringWindowToTop(hwnd)
    ctypes.windll.user32.SetForegroundWindow(hwnd)


def get_window_extents_by_title(window_title, exclude_titlebar=False):
    # TODO: check whether this is OK for ctypes, or we need to be stricter
    # with typing
    hwnd = ctypes.windll.user32.FindWindowW(0, window_title)
    if not hwnd:
        raise NoSuchWindowException(f"Can't find window '{window_title}'")
    # this gets the actual window bounds, excluding fancy Win10 drop shadow
    DWMWA_EXTENDED_FRAME_BOUNDS: int = 9
    rect = ctypes.wintypes.RECT()
    ret = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.pointer(rect),
        ctypes.sizeof(ctypes.wintypes.RECT))
    # DwmGetWindowAttribute(..) returns 0 on success
    if ret:
        raise NoSuchWindowException(f"DwmGetWindowAttribute(..) failed: {ret}")

    # TODO: this doesn't work correctly, titlebar height seems to depend on DPI scaling?
    if exclude_titlebar and False:
        SM_CYCAPTION: int = 4
        SM_CYSIZEFRAME: int = 33
        GetSystemMetrics = ctypes.windll.user32.GetSystemMetrics
        tbar_height = GetSystemMetrics(SM_CYCAPTION) + GetSystemMetrics(SM_CYSIZEFRAME) + 1
        rect.top += tbar_height
        rect.bottom -= tbar_height
        print(f"tbar_height: {tbar_height}")

    return (rect.left, rect.top, rect.right, rect.bottom)


class D3DShotPublisher(object):
    def __init__(self, dshot, img_width, img_height,
        frame_id="camera_rgb_optical_frame", ns="capture", pub_raw=True,
        pub_compressed=True, rate=30
    ):
        self._dshot = dshot
        self._img_width = img_width
        self._img_height = img_height
        self._frame_id = frame_id
        self._rate = rate
        self._pub_raw = None
        self._pub_compressed = None
        self._bridge = CvBridge()

        # the captures are essentially comparable to a rectified RGB image,
        # so use the correct topic name
        base_topic = f"{ns}/image_rect_color"

        # image publishers
        if pub_raw:
            self._pub_raw = rospy.Publisher(base_topic, Image, queue_size=1)
        if pub_compressed:
            self._pub_compressed = rospy.Publisher(f"{base_topic}/compressed",
                CompressedImage, queue_size=1)

        self._pub_cinfo = None
        if pub_raw or pub_compressed:
            self._pub_cinfo = rospy.Publisher(f"{base_topic}/camera_info",
                CameraInfo, queue_size=1)
        # we assume a static resolution here
        self._cam_info_msg = self._create_cam_info_msg(
            frame_id=frame_id, width=img_width, height=img_height)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # make sure to stop d3dshot capture thread
        self._dshot.stop()

    @property
    def _have_raw_subs(self):
        # if we aren't publishing to image_raw, we'll never have subs
        if self._pub_raw:
            return self._pub_raw.get_num_connections() > 0
        return False

    @property
    def _have_compressed_subs(self):
        # if we aren't publishing to compressed, we'll never have subs
        if self._pub_compressed:
            return self._pub_compressed.get_num_connections() > 0
        return False

    def spin(self):
        r = rospy.Rate(self._rate)
        while not rospy.is_shutdown():
            # TODO: could calculate and publish some statistics here
            self.spinOnce()
            r.sleep()

    def spinOnce(self):
        if not self._dshot.is_capturing:
            raise ValueError("d3dshot capture is not active")

        # check whether there is anyone interested in capture, if not, don't
        # do any unnecesary work
        have_raw_subs = self._have_raw_subs
        have_compressed_subs = self._have_compressed_subs
        if not (have_raw_subs or have_compressed_subs):
            return

        # grab the latest frame from the d3dshot queue
        img = self._dshot.get_latest_frame()

        # d3dshot capture is in RGB, OpenCV (and ROS) needs BGR, so convert.
        # insightful article: https://answers.opencv.org/question/219040
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        # this is actually not really true, the frame could (most likely was)
        # captured a bit in the past. But we can't retrieve that time, so
        # just use now()
        stamp = rospy.Time.now()

        # see what we need to publish:
        #
        #  - if we have subscribers for the raw image, convert and publish that
        #  - if we have subscribers for the compressed version, publish that
        #
        # Note: this could mean we:
        #
        #  - don't do anything (no subscribers at all)
        #  - we publish only the raw or the compressed image
        #  - we publish both

        if have_raw_subs:
            msg = self._bridge.cv2_to_imgmsg(img, encoding="passthrough")
            msg.header.stamp = stamp
            msg.header.frame_id = self._frame_id
            self._pub_raw.publish(msg)

        if have_compressed_subs:
            msg = self._bridge.cv2_to_compressed_imgmsg(img, dst_format="jpeg")
            msg.header.stamp = stamp
            msg.header.frame_id = self._frame_id
            self._pub_compressed.publish(msg)

        # if we have either, also publish a CameraInfo message
        if self._pub_cinfo and (have_raw_subs or have_compressed_subs):
            self._cam_info_msg.header.stamp = stamp
            self._pub_cinfo.publish(self._cam_info_msg)

    def _create_cam_info_msg(self, frame_id, width, height):
        msg = CameraInfo()
        msg.header.frame_id = frame_id
        msg.width = width
        msg.height = height

        # Spec (almost) default distortion model
        msg.distortion_model = "plumb_bob"
        # Spec default distortion matrix
        msg.D = [0.0]*5
        # Spec a (ok?) default intrinsic camera matrix
        msg.K = [width/2.0,        0.0,  width/2.0,
                       0.0, height/2.0, height/2.0,
                       0.0,        0.0,        1.0]
        # Spec a (ok?) default rectification matrix
        msg.R = [1.0, 0.0, 0.0,
                 0.0, 1.0, 0.0,
                 0.0, 0.0, 1.0]
        # Spec a (ok?) default projection matrix
        msg.P = [width/2.0,        0.0,  width/2.0, 0.0,
                       0.0, height/2.0, height/2.0, 0.0,
                       0.0,        0.0,        1.0, 0.0]
        return msg


if __name__ == '__main__':
    main()
