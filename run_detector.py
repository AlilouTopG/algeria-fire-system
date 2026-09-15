import os
import cv2
import time
import logging
import requests
from dotenv import load_dotenv
from ultralytics import YOLO
import db_manager as db

# تهيئة السجلات (Logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fire_detector.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("fire_detector")

# تحميل متغيرات البيئة
load_dotenv()

# تهيئة قاعدة البيانات المحلية والتأكد من جاهزيتها
db.init_db()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.38'))
ALERT_COOLDOWN = int(os.getenv('ALERT_COOLDOWN_SECONDS', '15'))
REGION_TAG = os.getenv('CAMERA_REGION', 'Bordj Bou Arreridj')
VERCEL_APP_URL = os.getenv('VERCEL_APP_URL')

# مسار الفيديو أو الكاميرا (0 للكاميرا المباشرة، أو اسم ملف فيديو)
VIDEO_SOURCE = os.getenv('VIDEO_SOURCE', 'test_video.mp4')
if not os.path.exists(VIDEO_SOURCE) and not str(VIDEO_SOURCE).isdigit():
    logger.warning(f"الملف {VIDEO_SOURCE} غير موجود، سيتم محاولة استخدام الكاميرا الافتراضية (0)...")
    VIDEO_SOURCE = 0


def send_telegram_alert(frame, label_name: str, confidence: float):
    """إرسال صورة التنبيه عبر التلغرام وحفظها"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.warning("لم يتم ضبط بيانات التلغرام في ملف .env")
        return False

    try:
        alert_img_path = "fire_alert.jpg"
        cv2.imwrite(alert_img_path, frame)
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        
        caption_text = (
            f"🚨 **إنذار حريق مبكر - المنظومة الوطنية**\n"
            f"📍 **المنطقة/الموقع:** {REGION_TAG}\n"
            f"⚠️ **نوع الخطر:** {label_name.upper()}\n"
            f"🎯 **نسبة التأكيد:** {confidence * 100:.1f}%\n"
            f"⏰ **التوقيت:** {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        with open(alert_img_path, "rb") as photo:
            payload = {"chat_id": CHAT_ID, "caption": caption_text, "parse_mode": "Markdown"}
            files = {"photo": photo}
            res = requests.post(url, data=payload, files=files, timeout=12)
            res.raise_for_status()
            logger.info(f"تم إرسال التنبيه إلى التلغرام بنجاح: {label_name}")
            return True
    except Exception as e:
        logger.error(f"فشل إرسال التنبيه إلى التلغرام: {e}")
        return False


def send_vercel_alert(label_name: str, confidence: float):
    """إرسال الإنذار لحظياً إلى منصة Vercel السحابية"""
    if not VERCEL_APP_URL:
        return False

    try:
        url = f"{VERCEL_APP_URL.rstrip('/')}/api/alerts"
        payload = {
            "region_id": REGION_TAG,
            "hazard_type": label_name,
            "confidence": float(confidence),
            "source": "AI Camera (Local Edge)"
        }
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code in [200, 201]:
            logger.info("تمت مزامنة الإنذار مع منصة Vercel بنجاح!")
            return True
    except Exception as e:
        logger.error(f"فشلت المزامنة مع Vercel: {e}")
    return False


def main():
    # تحميل نموذج الذكاء الاصطناعي
    model_path = "best.pt" if os.path.exists("best.pt") else "yolov8n.pt"
    logger.info(f"جاري تحميل النموذج: {model_path} ...")
    try:
        model = YOLO(model_path)
        logger.info("تم تحميل النموذج بنجاح!")
    except Exception as e:
        logger.error(f"خطأ في تحميل النموذج: {e}")
        return

    # تشغيل مدخل الفيديو / الكاميرا
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        logger.error(f"تعذر فتح مصدر الفيديو: {VIDEO_SOURCE}")
        return

    logger.info("بدأ فحص ومراقبة البث الحي...")

    last_alert_time = 0
    consecutive_detections = 0
    CONSECUTIVE_REQUIRED = 5  # فلتر التثبت: يجب رصد الخطر في 5 إطارات متتالية لتأكيد الحريق

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            logger.info("انتهى مقطع الفيديو أو تم قطع اتصال الكاميرا.")
            break

        # معالجة الإطار بالذكاء الاصطناعي
        results = model(frame, conf=CONFIDENCE_THRESHOLD, stream=True, verbose=False)

        frame_has_hazard = False
        highest_conf = 0.0
        detected_label = ""

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = model.names[cls_id]
                conf = float(box.conf[0])

                if label.lower() in ["fire", "smoke", "حريق", "دخان"]:
                    frame_has_hazard = True
                    if conf > highest_conf:
                        highest_conf = conf
                        detected_label = label

            # رسم المربعات التوضيحية فوق الفيديو
            frame = r.plot()

        # تطبيق فلتر التثبت الزمني لمنع الرمشات الكاذبة
        if frame_has_hazard:
            consecutive_detections += 1
        else:
            consecutive_detections = max(0, consecutive_detections - 1)

        current_time = time.time()

        # إطلاق الإنذار فقط عند تجاوز عدد الإطارات المشبوهة المتتالية
        if consecutive_detections >= CONSECUTIVE_REQUIRED:
            if current_time - last_alert_time > ALERT_COOLDOWN:
                logger.warning(f"تم تأكيد رصد خطر مؤكد ({detected_label}) بدقة {highest_conf:.2f}!")

                # 1. التسجيل في قاعدة البيانات المحلية
                db.add_alert(
                    region_id=REGION_TAG,
                    hazard_type=detected_label,
                    confidence=highest_conf,
                    source="Live Camera (AI)"
                )

                # 2. إرسال الصورة والبيانات إلى التلغرام
                send_telegram_alert(frame, detected_label, highest_conf)

                # 3. إرسال التنبيه فوراً إلى لوحة Vercel السحابية
                send_vercel_alert(detected_label, highest_conf)

                last_alert_time = current_time
                consecutive_detections = 0  # إعادة التصفير بعد إطلاق الإنذار

        # عرض نافذة المراقبة المباشرة
        try:
            cv2.imshow("نظام الرصد الذكي - البث المباشر", frame)
            if cv2.waitKey(20) & 0xFF == ord('q'):
                logger.info("تم إيقاف التشغيل بناءً على طلب المستخدم.")
                break
        except cv2.error:
            # في حال تشغيل النظام على بيئة بدون شاشة (Server / Headless)
            pass

    cap.release()
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass


if __name__ == "__main__":
    main()