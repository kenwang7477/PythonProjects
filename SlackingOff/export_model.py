from ultralytics import YOLO

print("載入 YOLO26n...")

model = YOLO("yolo26n.pt")

print("開始轉換 OpenVINO...")

model.export(
    format="openvino",
    imgsz=416,
    half=False
)

print("轉換完成！")
