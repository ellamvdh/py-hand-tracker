import mediapipe as mp
import cv2
import numpy as np
import time
import math
import requests
import base64

# ---------------------------
# Settings
# ---------------------------
FRAME_WIDTH, FRAME_HEIGHT = 640, 480
SPAWN_INTERVAL = 3       # seconds between butterfly spawns
BUTTERFLY_SIZE = 60      # pixels
MOVE_SPEED = 5           # hand repulsion speed
MAX_BUTTERFLIES = 30
API_URL = "https://vlinder-world.onrender.com/api/butterflies"
API_FETCH_INTERVAL = 15  # seconds between fetching new butterflies

# ---------------------------
# MediaPipe setup
# ---------------------------
mp_drawing = mp.solutions.drawing_utils
mp_hands = mp.solutions.hands

# ---------------------------
# Video capture
# ---------------------------
cap = cv2.VideoCapture(0)

# ---------------------------
# Butterfly storage
# ---------------------------
butterfly_images = []    # NumPy arrays for images
butterfly_sources = []   # Track which images have been loaded
last_api_fetch = 0

def fetch_butterflies():
    global butterfly_images, butterfly_sources, last_api_fetch
    try:
        response = requests.get(API_URL)
        data = response.json()
        added = 0
        for b in data:
            img_str = b.get("image") or b.get("img") or b.get("url")
            if not img_str:
                continue

            # Skip if we already loaded this image
            if img_str in butterfly_sources:
                continue

            # Decode image
            if img_str.startswith("data:image"):
                base64_str = img_str.split(",")[1]
                img_data = base64.b64decode(base64_str)
                img_array = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
            else:
                img_data = requests.get(img_str).content
                img_array = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)

            img = cv2.resize(img, (BUTTERFLY_SIZE, BUTTERFLY_SIZE))
            butterfly_images.append(img)
            butterfly_sources.append(img_str)
            added += 1

        last_api_fetch = time.time()
        if added > 0:
            print(f"Fetched {added} new butterfly(ies), total: {len(butterfly_images)}")

    except Exception as e:
        print("Failed to fetch butterflies:", e)

# Initial fetch
fetch_butterflies()

# ---------------------------
# Track butterflies
# ---------------------------
butterflies = []
last_spawn_time = 0

# ---------------------------
# Hand detection loop
# ---------------------------
with mp_hands.Hands(
    static_image_mode=False,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7,
    max_num_hands=2
) as hands:

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        canvas = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        hand_points = []

        # ---------------------------
        # Draw hands & collect landmarks
        # ---------------------------
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(canvas, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                for lm in hand_landmarks.landmark:
                    x = int(lm.x * FRAME_WIDTH)
                    y = int(lm.y * FRAME_HEIGHT)
                    hand_points.append((x, y))

        # ---------------------------
        # Fetch new butterflies periodically
        # ---------------------------
        if time.time() - last_api_fetch > API_FETCH_INTERVAL:
            fetch_butterflies()

        # ---------------------------
        # Spawn butterfly at index fingertip
        # ---------------------------
        current_time = time.time()
        if results.multi_hand_landmarks and (current_time - last_spawn_time >= SPAWN_INTERVAL):
            lm = results.multi_hand_landmarks[0].landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            x = int(lm.x * FRAME_WIDTH)
            y = int(lm.y * FRAME_HEIGHT)

            # Prevent overlapping spawn
            safe = True
            for b in butterflies:
                if math.hypot(b['x'] - x, b['y'] - y) < BUTTERFLY_SIZE:
                    safe = False
                    break

            if safe and butterfly_images:
                # Spawn the latest butterfly
                butterflies.append({
                    'x': x,
                    'y': y,
                    'img': butterfly_images[-1]
                })
                last_spawn_time = current_time

            # Limit max butterflies
            if len(butterflies) > MAX_BUTTERFLIES:
                butterflies.pop(0)

        # ---------------------------
        # Move butterflies away from hands
        # ---------------------------
        for b in butterflies:
            for hx, hy in hand_points:
                dx = b['x'] - hx
                dy = b['y'] - hy
                dist = math.hypot(dx, dy)
                if dist < BUTTERFLY_SIZE // 2:
                    if dist == 0:
                        dx, dy = 1, 0
                        dist = 1
                    b['x'] += int(dx / dist * MOVE_SPEED)
                    b['y'] += int(dy / dist * MOVE_SPEED)
                    b['x'] = np.clip(b['x'], BUTTERFLY_SIZE//2, FRAME_WIDTH - BUTTERFLY_SIZE//2)
                    b['y'] = np.clip(b['y'], BUTTERFLY_SIZE//2, FRAME_HEIGHT - BUTTERFLY_SIZE//2)

        # ---------------------------
        # Draw butterflies
        # ---------------------------
        for b in butterflies:
            img = b['img']
            h, w = img.shape[:2]
            x1 = b['x'] - w // 2
            y1 = b['y'] - h // 2
            x2 = x1 + w
            y2 = y1 + h

            if x1 >= 0 and y1 >= 0 and x2 <= FRAME_WIDTH and y2 <= FRAME_HEIGHT:
                if img.shape[2] == 4:  # PNG with alpha
                    alpha = img[:, :, 3] / 255.0
                    for c in range(3):
                        canvas[y1:y2, x1:x2, c] = (
                            alpha * img[:, :, c] +
                            (1 - alpha) * canvas[y1:y2, x1:x2, c]
                        )
                else:
                    canvas[y1:y2, x1:x2] = img

        # ---------------------------
        # Show canvas
        # ---------------------------
        cv2.imshow("Butterfly Garden", canvas)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()