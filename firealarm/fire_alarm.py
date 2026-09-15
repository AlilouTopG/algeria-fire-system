import cv2
import requests
import time
from ultralytics import YOLO

# 1. إعداد بيانات بوت التلغرام (استبدل القيم بحسابك الحقيقي)
TELEGRAM_TOKEN = "ضع_هنا_API_TOKEN_الخاص_ببوتينك"
CHAT_ID = "ضع_هنا_CHAT_ID_الخاص_بك"

def send_telegram_alert(frame, text):
    """دالة تقوم بحفظ الصورة الحالية وإرسالها إلى التلغرام مع نص التنبيه"""
    # حفظ الإطار الحالي كصورة وقتية
    cv2.imwrite("fire_alert.jpg", frame)
    
    # رابط إرسال الصور عبر التلغرام
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    # فتح الصورة وإرسالها
    with open("fire_alert.jpg", "rb") as image_file:
        payload = {"chat_id": CHAT_ID, "caption": text}
        files = {"photo": image_file}
        try:
            requests.post(url, data=payload, files=files)
            print("تم إرسال التنبيه إلى التلغرام بنجاح!")
        except Exception as e:
            print("خطأ في إرسال التنبيه:", e)

# 2. تحميل نموذج الذكاء الاصطناعي (سينزل تلقائياً في أول مرة)
model = YOLO("yolov8n.pt")

# 3. تشغيل كاميرا الحاسوب (الرقم 0 يعني الكاميرا المدمجة)
cap = cv2.VideoCapture(0)

# متغيرات للتحكم في زمن التنبيه (كي لا يرسل آلاف الرسائل في الثانية)
last_alert_time = 0
ALERT_COOLDOWN = 10  # إرسال تنبيه واحد كل 10 ثوانٍ كأقصى حد

print("جاري تشغيل النظام... اضغط 'q' للخروج")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    # تمرير الصورة للذكاء الاصطناعي للتحليل
    results = model(frame, stream=True, conf=0.5)

    fire_detected = False

    for r in results:
        boxes = r.boxes
        for box in boxes:
            # لمعرفة اسم الشيء المكتشف
            class_id = int(box.cls[0])
            class_name = model.names[class_id]

            # في النموذج المخصص سنفحص 'fire' أو 'smoke'
            # حالياً سنفحص كمثال (أو عند استخدام نموذج مدرب على النار)
            if class_name in ["fire", "smoke"]:
                fire_detected = True

        # رسم المربعات فوق الصورة للتوضيح Visual Feedback
        frame = r.plot()

    # إذا تم كشف خطر ومرت 10 ثوانٍ على آخر تنبيه
    current_time = time.time()
    if fire_detected and (current_time - last_alert_time > ALERT_COOLDOWN):
        print("خطر! تم رصد حريق/دخان!")
        send_telegram_alert(frame, "⚠️ تحذير عاجل: تم رصد دخان أو حريق في الموقع!")
        last_alert_time = current_time

    # عرض البث الحي على الشاشة
    cv2.imshow("نظام الكشف المبكر عن الحرائق - OpenCode", frame)

    # الخروج عند الضغط على حرف q
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# إغلاق الكاميرا والنوافذ
cap.release()
cv2.destroyAllWindows()