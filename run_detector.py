import os
import cv2
import requests
import time
import logging
from dotenv import load_dotenv
from ultralytics import YOLO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fire_detector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# 1. بيانات التلغرام من متغيرات البيئة
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TELEGRAM_TOKEN or not CHAT_ID:
    logger.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env file")
    raise EnvironmentError("Missing required environment variables")

def send_telegram_alert(frame, label_name):
    """حفظ الصورة وإرسالها فوراً إلى التلغرام"""
    try:
        cv2.imwrite("fire_alert.jpg", frame)
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        caption_text = f"⚠️ **تحذير عاجل**: تم رصد ({label_name}) في الموقع!"
        
        with open("fire_alert.jpg", "rb") as photo:
            payload = {"chat_id": CHAT_ID, "caption": caption_text}
            files = {"photo": photo}
            response = requests.post(url, data=payload, files=files, timeout=30)
            response.raise_for_status()
            logger.info(f"Telegram alert sent successfully for {label_name}")
            return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram alert: {e}")
        return False

# 2. تحميل الفيديو والنموذج
video_path = "test_video.mp4"
if not os.path.exists(video_path):
    logger.error(f"Video file not found: {video_path}")
    raise FileNotFoundError(f"Video file not found: {video_path}")

logger.info("Loading AI model best.pt...")
try:
    model = YOLO("best.pt")
    logger.info("Model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load model: {e}")
    raise

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    logger.error(f"Failed to open video file: {video_path}")
    raise RuntimeError(f"Failed to open video file: {video_path}")

last_alert_time = 0
ALERT_COOLDOWN = 10 

logger.info("Starting video analysis and alert system...")

while cap.isOpened():
    try:
        success, frame = cap.read()
        if not success:
            logger.info("End of video stream")
            break

        # تحليل الإطار بواسطة النموذج
        results = model(frame, conf=0.5, stream=True)

        detected_hazard = False
        detected_class_name = ""

        for r in results:
            boxes = r.boxes
            for box in boxes:
                class_id = int(box.cls[0])
                class_name = model.names[class_id]

                if class_name in ["fire", "smoke"]:
                    detected_hazard = True
                    detected_class_name = class_name
                    logger.debug(f"Detected: {class_name} with confidence {float(box.conf[0]):.2f}")

            frame = r.plot()

        current_time = time.time()
        if detected_hazard and (current_time - last_alert_time > ALERT_COOLDOWN):
            if send_telegram_alert(frame, detected_class_name):
                last_alert_time = current_time
                logger.info(f"Alert sent for {detected_class_name}")

        # عرض البث الحي إذا كانت الشاشة مدعومة
        try:
            cv2.imshow("Fire & Smoke Detector - OpenCode", frame)
            if cv2.waitKey(25) & 0xFF == ord('q'):
                logger.info("User requested exit")
                break
        except cv2.error:
            # Headless environment - skip display
            pass
    except Exception as e:
        logger.error(f"Error processing frame: {e}")
        continue

cap.release()
try:
    cv2.destroyAllWindows()
except cv2.error:
    pass

logger.info("System shutdown complete")