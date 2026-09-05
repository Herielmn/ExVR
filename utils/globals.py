from threading import Event

import cv2

LATEST_DATA_SIZE = 64 + 6 + 12 + 10 + 12 + 10 + 3 + 2 + 10

config: dict = {}
data: dict = {}
default_data: dict = {}
hotkey_config: dict = {}
smoothing_config: dict = {}
gesture_config: dict = {}
controller = None

kalman_filters: dict = {}
indices_map: dict = {}

latest_data = [0.0] * LATEST_DATA_SIZE
current_fps = 30
stop_event = Event()

face_landmarks = None
hand_landmarks = None
handedness = None

tongue_model = None
face_detector = None
hand_detector = None
hand_feature_model = None
hand_regression_model = None

start_time = cv2.getTickCount()
