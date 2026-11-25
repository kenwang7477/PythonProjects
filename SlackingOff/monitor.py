import os
import time

import cv2
import psutil
import win32gui
import win32con
import torch

from ultralytics import YOLO


# =====================================================
# 1. 基本設定
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_DIR = os.path.join(
    BASE_DIR,
    "yolo26n_openvino_model"
)

CAMERA_INDEX = 0

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 320
CAMERA_FPS = 15

IMAGE_SIZE = 416

# OpenVINO Intel GPU
DEVICE = "xpu"

CONFIDENCE = 0.5

# YOLO 每 0.4 秒辨識一次
DETECTION_INTERVAL = 0.4

# PiP 每 1 秒檢查一次
PIP_CHECK_INTERVAL = 1.0

# 同一視窗關閉重試間隔
PIP_RETRY_INTERVAL = 2.0

# PiP 最大尺寸
PIP_MAX_WIDTH = 1000
PIP_MAX_HEIGHT = 800

# CPU 執行緒
CPU_THREADS = 2

WINDOW_NAME = "AI Security Monitor"


# =====================================================
# 2. CPU 最佳化
# =====================================================

cv2.setNumThreads(1)

torch.set_num_threads(CPU_THREADS)

try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass


# =====================================================
# 3. 確認模型
# =====================================================

if not os.path.isdir(MODEL_DIR):
    print("找不到 OpenVINO 模型資料夾！")
    print(MODEL_DIR)
    raise SystemExit


# =====================================================
# 4. 載入 YOLO
# =====================================================

print("正在載入 YOLOv8n OpenVINO...")

model = YOLO(MODEL_DIR)

print("模型載入完成！")


# =====================================================
# 5. 開啟攝影機
# =====================================================

camera = cv2.VideoCapture(
    CAMERA_INDEX,
    cv2.CAP_DSHOW
)

if not camera.isOpened():
    print("攝影機開啟失敗！")
    raise SystemExit

camera.set(
    cv2.CAP_PROP_FRAME_WIDTH,
    CAMERA_WIDTH
)

camera.set(
    cv2.CAP_PROP_FRAME_HEIGHT,
    CAMERA_HEIGHT
)

camera.set(
    cv2.CAP_PROP_FPS,
    CAMERA_FPS
)

camera.set(
    cv2.CAP_PROP_BUFFERSIZE,
    1
)


# =====================================================
# 6. 全域狀態
# =====================================================

roi = None

drawing = False
start_point = None
end_point = None

monitoring = False
detection_paused = False

person_detected = False
previous_person_detected = False

detected_boxes = []

last_detection_time = 0
last_pip_check_time = 0

pip_status = "WAITING"

close_requested = {}

process = psutil.Process(os.getpid())
process.cpu_percent(None)


# =====================================================
# 7. 搜尋 YouTube PiP
# =====================================================

def find_youtube_pip():

    targets = []

    def enum_windows(hwnd, extra):

        if not win32gui.IsWindowVisible(hwnd):
            return

        try:

            title = win32gui.GetWindowText(hwnd)

            if not title:
                return

            class_name = win32gui.GetClassName(hwnd)

            if class_name != "Chrome_WidgetWin_1":
                return

            title_lower = title.lower()

            pip_keywords = [
                "picture-in-picture",
                "picture in picture",
                "子母畫面",
                "畫中畫"
            ]

            youtube_keywords = [
                "youtube"
            ]

            is_pip_title = any(
                keyword in title_lower
                for keyword in pip_keywords
            )

            is_youtube_title = any(
                keyword in title_lower
                for keyword in youtube_keywords
            )

            if not (
                is_pip_title or is_youtube_title
            ):
                return

            left, top, right, bottom = (
                win32gui.GetWindowRect(hwnd)
            )

            width = right - left
            height = bottom - top

            if not (
                0 < width <= PIP_MAX_WIDTH
                and 0 < height <= PIP_MAX_HEIGHT
            ):
                return

            targets.append({
                "hwnd": hwnd,
                "title": title,
                "width": width,
                "height": height
            })

        except Exception:
            pass

    win32gui.EnumWindows(
        enum_windows,
        None
    )

    return targets


# =====================================================
# 8. 關閉 YouTube PiP
# =====================================================

def close_youtube_pip():

    global close_requested

    current_time = time.time()

    # 清除已經不存在的視窗
    for hwnd in list(close_requested.keys()):

        if not win32gui.IsWindow(hwnd):
            del close_requested[hwnd]

    try:

        targets = find_youtube_pip()

        if not targets:
            return False

        close_success = False

        for item in targets:

            hwnd = item["hwnd"]

            previous_time = close_requested.get(
                hwnd,
                0
            )

            if (
                current_time - previous_time
                < PIP_RETRY_INTERVAL
            ):
                continue

            # print(
            #     "找到 YouTube PiP：",
            #     item["title"]
            # )

            try:
                win32gui.PostMessage(
                    hwnd,
                    win32con.WM_CLOSE,
                    0,
                    0
                )

                close_requested[hwnd] = current_time

                # print("已要求關閉 PiP")

                close_success = True

            except Exception as e:

                print("PiP 關閉失敗：", e)

        return close_success

    except Exception as e:

        print("PiP 搜尋錯誤：", e)

        return False


# =====================================================
# 9. ROI 滑鼠框選
# =====================================================

def mouse_callback(event, x, y, flags, param):

    global drawing
    global start_point
    global end_point
    global roi

    if monitoring:
        return

    if event == cv2.EVENT_LBUTTONDOWN:

        drawing = True

        start_point = (x, y)
        end_point = (x, y)

    elif event == cv2.EVENT_MOUSEMOVE and drawing:

        end_point = (x, y)

    elif event == cv2.EVENT_LBUTTONUP:

        drawing = False

        if start_point is None:
            return

        x1 = min(start_point[0], x)
        y1 = min(start_point[1], y)

        x2 = max(start_point[0], x)
        y2 = max(start_point[1], y)

        if x2 - x1 > 10 and y2 - y1 > 10:

            roi = (
                x1,
                y1,
                x2,
                y2
            )

            print("ROI 設定完成：", roi)

# =====================================================
# 10. 初始化視窗
# =====================================================

cv2.namedWindow(WINDOW_NAME)

cv2.setMouseCallback(
    WINDOW_NAME,
    mouse_callback
)

print("")
print("======================================")
print("         AI SECURITY MONITOR")
print("======================================")
print("滑鼠拖曳：選擇監控區域")
print("S：開始監控")
print("P：暫停 / 恢復偵測")
print("R：重新選擇 ROI")
print("Q：結束程式")
print("======================================")


# =====================================================
# 11. 主監控迴圈
# =====================================================

try:

    while True:

        ret, frame = camera.read()

        if not ret:
            time.sleep(0.05)
            continue

        frame = cv2.flip(frame, 1)
        display = frame.copy()

        current_time = time.time()

        # ---------------------------------------------
        # 顯示 ROI
        # ---------------------------------------------

        if drawing and start_point and end_point:

            cv2.rectangle(
                display,
                start_point,
                end_point,
                (0, 255, 255),
                2
            )

        if roi:

            x1_roi, y1_roi, x2_roi, y2_roi = roi

            cv2.rectangle(
                display,
                (x1_roi, y1_roi),
                (x2_roi, y2_roi),
                (0, 255, 0),
                2
            )

        # ---------------------------------------------
        # YOLO 人物辨識
        # ---------------------------------------------

        if monitoring and roi and not detection_paused:

            if (
                current_time - last_detection_time
                >= DETECTION_INTERVAL
            ):

                last_detection_time = current_time

                person_detected = False
                detected_boxes = []

                results = model.predict(
                    frame,
                    classes=[0],
                    conf=CONFIDENCE,
                    imgsz=IMAGE_SIZE,
                    device=DEVICE,
                    verbose=False
                )

                for result in results:

                    for box in result.boxes:

                        bx1, by1, bx2, by2 = map(
                            int,
                            box.xyxy[0].tolist()
                        )

                        # 人物中心點
                        cx = (bx1 + bx2) // 2
                        cy = (by1 + by2) // 2

                        # 判斷人物是否在 ROI
                        if (
                            x1_roi <= cx <= x2_roi
                            and
                            y1_roi <= cy <= y2_roi
                        ):

                            person_detected = True

                            detected_boxes.append(
                                (
                                    bx1,
                                    by1,
                                    bx2,
                                    by2,
                                    cx,
                                    cy
                                )
                            )

                # -------------------------------------
                # 人物進入 ROI
                # -------------------------------------

                if (
                    person_detected
                    and not previous_person_detected
                ):

                    # print("人物進入 ROI！")

                    last_pip_check_time = 0

                # -------------------------------------
                # 人物離開 ROI
                # -------------------------------------

                elif (
                    not person_detected
                    and previous_person_detected
                ):

                    # print("人物離開 ROI！")

                    pip_status = "WAITING"

                    last_pip_check_time = 0

                previous_person_detected = person_detected

            # -----------------------------------------
            # PiP 每秒檢查
            # -----------------------------------------

            if person_detected:

                if (
                    current_time - last_pip_check_time
                    >= PIP_CHECK_INTERVAL
                ):

                    last_pip_check_time = current_time

                    # print("檢查 YouTube PiP...")

                    if close_youtube_pip():

                        pip_status = "CLOSE REQUESTED"

                    else:

                        pip_status = "WAITING / NO NEW REQUEST"

            # -----------------------------------------
            # 顯示人物框
            # -----------------------------------------

            for data in detected_boxes:

                bx1, by1, bx2, by2, cx, cy = data

                cv2.rectangle(
                    display,
                    (bx1, by1),
                    (bx2, by2),
                    (0, 0, 255),
                    2
                )

                cv2.circle(
                    display,
                    (cx, cy),
                    4,
                    (0, 0, 255),
                    -1
                )

        # ---------------------------------------------
        # 顯示監控狀態
        # ---------------------------------------------

        if detection_paused:

            status_text = "DETECTION PAUSED"
            status_color = (0, 255, 255)

        elif not monitoring:

            status_text = "SELECT ROI - PRESS S"
            status_color = (0, 255, 255)

        elif person_detected:

            status_text = "PERSON DETECTED"
            status_color = (0, 0, 255)

        else:

            status_text = "MONITORING"
            status_color = (0, 255, 0)

        cv2.putText(
            display,
            status_text,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            status_color,
            2
        )

        # ---------------------------------------------
        # PiP 狀態
        # ---------------------------------------------

        # cv2.putText(
        #     display,
        #     "YouTube PiP: " + pip_status,
        #     (20, 80),
        #     cv2.FONT_HERSHEY_SIMPLEX,
        #     0.5,
        #     (255, 255, 0),
        #     1
        # )

        # ---------------------------------------------
        # CPU 使用率
        # ---------------------------------------------

        # cpu_usage = process.cpu_percent(None)

        # cv2.putText(
        #     display,
        #     f"CPU: {cpu_usage:.1f}%",
        #     (20, 110),
        #     cv2.FONT_HERSHEY_SIMPLEX,
        #     0.5,
        #     (255, 255, 255),
        #     1
        # )

        # ---------------------------------------------
        # YOLO 偵測頻率
        # ---------------------------------------------

        # cv2.putText(
        #     display,
        #     f"YOLO: {1 / DETECTION_INTERVAL:.1f} Hz",
        #     (20, 140),
        #     cv2.FONT_HERSHEY_SIMPLEX,
        #     0.5,
        #     (255, 255, 255),
        #     1
        # )

        # ---------------------------------------------
        # PiP 檢查頻率
        # ---------------------------------------------

        # cv2.putText(
        #     display,
        #     f"PIP CHECK: {PIP_CHECK_INTERVAL:.1f}s",
        #     (20, 170),
        #     cv2.FONT_HERSHEY_SIMPLEX,
        #     0.5,
        #     (255, 255, 255),
        #     1
        # )

        # ---------------------------------------------
        # 顯示畫面
        # ---------------------------------------------

        cv2.imshow(
            WINDOW_NAME,
            display
        )

        # ---------------------------------------------
        # 鍵盤操作
        # ---------------------------------------------

        key = cv2.waitKey(1) & 0xFF

        # =============================================
        # S：開始監控
        # =============================================

        if key == ord('s'):

            if roi:

                monitoring = True
                detection_paused = False

                person_detected = False
                previous_person_detected = False

                detected_boxes = []

                last_detection_time = 0
                last_pip_check_time = 0

                close_requested.clear()

                print("監控開始！")

            else:

                print("請先選擇 ROI！")

        # =============================================
        # P：暫停 / 恢復偵測
        # =============================================

        elif key == ord('p'):

            if monitoring:

                detection_paused = not detection_paused

                if detection_paused:

                    # print("人物偵測已暫停")

                    person_detected = False
                    previous_person_detected = False

                    detected_boxes = []

                    pip_status = "DETECTION PAUSED"

                else:

                    # print("人物偵測已恢復")

                    person_detected = False
                    previous_person_detected = False

                    detected_boxes = []

                    last_detection_time = 0
                    last_pip_check_time = 0

                    close_requested.clear()

                    pip_status = "WAITING"

            else:

                print("請先按 S 開始監控！")

        # =============================================
        # R：重新選擇 ROI
        # =============================================

        elif key == ord('r'):

            roi = None

            monitoring = False
            detection_paused = False

            person_detected = False
            previous_person_detected = False

            detected_boxes = []

            close_requested.clear()

            pip_status = "WAITING"

            print("請重新選擇監控區域！")

        # =============================================
        # Q：結束程式
        # =============================================

        elif key == ord('q'):

            print("結束監控！")

            break


# =====================================================
# 12. 釋放資源
# =====================================================

finally:

    camera.release()

    cv2.destroyAllWindows()

    print("AI Security Monitor 已關閉！")