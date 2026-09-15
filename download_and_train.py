import os
import shutil
from ultralytics import YOLO

# ==========================================================
# 1. إعداد مسار البيانات (Dataset)
# ==========================================================
# إذا كان لديك ملف data.yaml محلي للصور الموجودة على حاسوبك، ضع مساره هنا.
# إذا لم يكن موجوداً، سيقوم السكريبت بتنزيل داتاسيت غابات عالية الجودة من Roboflow.
LOCAL_DATA_YAML = "data.yaml"

if os.path.exists(LOCAL_DATA_YAML):
    yaml_path = os.path.abspath(LOCAL_DATA_YAML)
    print(f"تم العثور على ملف البيانات المحلي: {yaml_path}")
else:
    print("جاري الاتصال وسحب داتاسيت حرائق الغابات المتخصصة...")
    from roboflow import Roboflow
    rf = Roboflow(api_key=os.getenv("ROBOFLOW_API_KEY", "sJKda03AskC1OQlGB8yZ"))
    
    # داتاسيت متخصصة في الدخان وحرائق الأحراش والغابات
    project = rf.workspace("wildfire-detection-ai").project("forest-fire-smoke-algeria")
    version = project.version(1)
    dataset = version.download("yolov8")
    yaml_path = os.path.join(dataset.location, "data.yaml")

# ==========================================================
# 2. اختيار النموذج وضبط المعاملات المتقدمة
# ==========================================================
print("\nجاري تحميل أوزان نموذج YOLOv8s المتقدم...")
# نستخدم yolov8s لأنه يمتلك قدرة أعلى بكثير على تمييز الدخان والغيوم مقارنة بـ nano
model = YOLO("yolov8s.pt")

print("\nبدء التدريب المتطور لمعالجة الإنذارات الكاذبة (False Positives)...")

results = model.train(
    data=yaml_path,
    epochs=70,             # زيادة الحلقات ليتعلم النموذج الأنماط المعقدة للدخان
    patience=15,           # التوقف التلقائي إذا وصل النموذج لأعلى دقة
    imgsz=640,             # الدقة المناسبة لمعالجة الكاميرات
    batch=16,              # حجم الدفعة (يمكن تقليله لـ 8 إذا كانت ذاكرة GPU صغيرة)
    name="wildfire_sovereign_model",
    workers=4,
    
    # معاملات خاصة بحرائق الغابات لتقليل الأخطاء:
    mosaic=1.0,            # دمج 4 صور لتدريب النموذج على كشف الحرائق الصغيرة والبعيدة
    mixup=0.1,             # دمج خلفيات مختلفة لمنع الخلط بين السحب والدخان
    hsv_h=0.015,           # محاكاة تغير درجات اللون
    hsv_s=0.7,             # محاكاة تشبع الألوان في الصيف الجزائري
    hsv_v=0.4,             # محاكاة التباين بين الظل والشمس الساطعة
    degrees=10.0,          # تدوير خفيف للصور
    fliplr=0.5,            # قلب الصور أفقياً
    verbose=True
)

print("\nاكتمل التدريب بنجاح تام!")
best_model_path = os.path.join("runs", "detect", "wildfire_sovereign_model", "weights", "best.pt")

if os.path.exists(best_model_path):
    shutil.copy(best_model_path, "best.pt")
    print(f"تم نسخ النموذج الأفضل تلقائياً إلى المجلد الرئيسي باسم: best.pt")
    print("النموذج الآن جاهز للاستخدام مباشرة مع run_detector.py بدون أي تعديل إضافي!")