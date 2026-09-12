import os
from roboflow import Roboflow
from ultralytics import YOLO

# 1. مفتاح الـ API الخاص بك
API_KEY = "sJKda03AskC1OQlGB8yZ"

# 2. جلب وتنزيل مجموعة البيانات مباشرة من Roboflow
print("جاري الاتصال بـ Roboflow وتنزيل مجموعة البيانات (Dataset)...")
rf = Roboflow(api_key=API_KEY)
project = rf.workspace("lee-ho-yeong").project("fire-and-smoke-zcztx")
version = project.version(1)

# تنزيل البيانات بصيغة YOLOv8
dataset = version.download("yolov8")

# 3. تحديد مسار ملف التهيئة data.yaml
yaml_path = os.path.join(dataset.location, "data.yaml")

# 4. تحميل نموذج YOLOv8 الخفيف
model = YOLO("yolov8n.pt")

# 5. بدء تدريب الذكاء الاصطناعي على صور الحرائق والدخان
print("\nتم التنزيل بنجاح! جاري بدء تدريب النموذج الآن...")
results = model.train(
    data=yaml_path,
    epochs=30,       # عدد دورات التدريب (يمكنك زيادتها لاحقاً لـ 50 لدقة أفضل)
    imgsz=640,       # دقة الصور أثناء التدريب
    batch=16,        # عدد الصور في كل دفعة
    name="fire_smoke_model"
)

print("\nمبروك يا صديقي! اكتمل التدريب بنجاح.")
print("ستجد الملف النهائي باسم best.pt داخل المجلد:")
print("runs/detect/fire_smoke_model/weights/best.pt")