import mediapipe as mp
import cv2
import numpy as np
import time
import math
import requests
import base64
import threading
import random
import tkinter as tk

# ---------------------------
# Fullscreen resolution
# ---------------------------
root = tk.Tk()
SCREEN_WIDTH = root.winfo_screenwidth()
SCREEN_HEIGHT = root.winfo_screenheight()
root.destroy()
FRAME_WIDTH, FRAME_HEIGHT = SCREEN_WIDTH, SCREEN_HEIGHT

# ---------------------------
# Settings
# ---------------------------
SPAWN_INTERVAL = 2
BUTTERFLY_SIZE = 60
MAX_BUTTERFLIES = 30
MAX_CACHED_BUTTERFLIES = 15
API_URL = "https://vlinder-world.onrender.com/api/butterflies"
API_FETCH_INTERVAL = 30

# Physics
REPULSION_RADIUS = 120
REPULSION_FORCE = 1.8
DAMPING = 0.92
WANDER_STRENGTH = 0.5
MAX_SPEED = 6

# Wing flap
FLAP_AMPLITUDE = 0.25
FLAP_SPEED = 3.0

# Image flip mode: 0=verticaal, 1=horizontaal, -1=beide
FLIP_MODE = 1

# ---------------------------
# MediaPipe setup
# ---------------------------
mp_drawing = mp.solutions.drawing_utils
mp_hands = mp.solutions.hands

# ---------------------------
# Fullscreen window
# ---------------------------
cv2.namedWindow("Butterfly Garden", cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty("Butterfly Garden", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

# ---------------------------
# Butterfly cache
# ---------------------------
butterfly_images = []
butterfly_sources = []

def fetch_butterflies():
    global butterfly_images, butterfly_sources
    try:
        response = requests.get(API_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        added = 0
        for b in data[:10]:
            img_str = b.get("image") or b.get("img") or b.get("url")
            if not img_str or img_str in butterfly_sources:
                continue
            try:
                if img_str.startswith("data:image"):
                    img_data = base64.b64decode(img_str.split(",")[1])
                else:
                    img_data = requests.get(img_str, timeout=5).content
                img_array = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
                if img is None:
                    continue
                img = cv2.resize(img, (BUTTERFLY_SIZE, BUTTERFLY_SIZE))
                butterfly_images.append(img)
                butterfly_sources.append(img_str)
                added += 1
                if len(butterfly_images) > MAX_CACHED_BUTTERFLIES:
                    butterfly_images.pop(0)
                    butterfly_sources.pop(0)
            except:
                continue
        if added:
            print(f"Fetched {added} new butterflies, cache size: {len(butterfly_images)}")
    except Exception as e:
        print("API error:", e)

threading.Thread(target=lambda: [fetch_butterflies() or time.sleep(API_FETCH_INTERVAL) for _ in iter(int, 1)], daemon=True).start()

# ---------------------------
# Butterflies
# ---------------------------
butterflies = []
last_spawn_time = 0

# ---------------------------
# Hand detection
# ---------------------------
cap = cv2.VideoCapture(0)
with mp_hands.Hands(static_image_mode=False, min_detection_confidence=0.7, min_tracking_confidence=0.7, max_num_hands=2) as hands:

    while True:
        canvas = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        hand_points = []

        ret, frame = cap.read()
        if not ret:
            continue

        # Resize for hand detection
        h_cam, w_cam = frame.shape[:2]
        scale = FRAME_HEIGHT / h_cam
        frame_resized = cv2.resize(frame, (int(w_cam*scale), FRAME_HEIGHT))
        rgb_frame = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        # Map hand coordinates
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                for lm in hand_landmarks.landmark:
                    x = int(lm.x * frame_resized.shape[1] * (FRAME_WIDTH / frame_resized.shape[1]))
                    y = int(lm.y * FRAME_HEIGHT)
                    hand_points.append((x, y))
                # Draw skeleton
                mp_drawing.draw_landmarks(
                    canvas, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(200, 200, 200), thickness=2)
                )

        # ---------------------------
        # Spawn butterfly
        # ---------------------------
        current_time = time.time()
        if results.multi_hand_landmarks and current_time - last_spawn_time > SPAWN_INTERVAL:
            lm = results.multi_hand_landmarks[0].landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            x = int(lm.x * FRAME_WIDTH)
            y = int(lm.y * FRAME_HEIGHT)
            if butterfly_images:
                butterflies.append({
                    'x': float(x), 'y': float(y),
                    'vx': random.uniform(-2, 2),
                    'vy': random.uniform(-2, 2),
                    'img': random.choice(butterfly_images),
                    'phase': random.uniform(0, 2*math.pi)
                })
                last_spawn_time = current_time
            if len(butterflies) > MAX_BUTTERFLIES:
                butterflies.pop(0)

        # ---------------------------
        # Physics + flapping
        # ---------------------------
        t = time.time()
        for b in butterflies:
            # Wander
            b['vx'] += random.uniform(-0.5, 0.5)
            b['vy'] += random.uniform(-0.5, 0.5)
            # Repulsion
            for hx, hy in hand_points:
                dx = b['x'] - hx
                dy = b['y'] - hy
                dist = math.hypot(dx, dy)
                if dist < 120 and dist > 0:
                    force = (120 - dist) / 120 * 1.8
                    b['vx'] += dx / dist * force
                    b['vy'] += dy / dist * force
            # Damping
            b['vx'] *= 0.92
            b['vy'] *= 0.92
            # Limit speed
            speed = math.hypot(b['vx'], b['vy'])
            if speed > 6:
                b['vx'] = (b['vx']/speed)*6
                b['vy'] = (b['vy']/speed)*6
            # Update position
            b['x'] += b['vx']
            b['y'] += b['vy']
            b['x'] = np.clip(b['x'], BUTTERFLY_SIZE//2, FRAME_WIDTH - BUTTERFLY_SIZE//2)
            b['y'] = np.clip(b['y'], BUTTERFLY_SIZE//2, FRAME_HEIGHT - BUTTERFLY_SIZE//2)

        # ---------------------------
        # Draw butterflies with horizontal wing flap
        # ---------------------------
        for b in butterflies:
            img = b['img']
            h, w = img.shape[:2]
            flap = 1 + FLAP_AMPLITUDE * math.sin(2*math.pi*FLAP_SPEED*t + b['phase'])
            new_w = max(1, int(w * flap))
            img_flap = cv2.resize(img, (new_w, h), interpolation=cv2.INTER_LINEAR)
            x1 = int(b['x'] - new_w/2)
            y1 = int(b['y'] - h/2)
            x2, y2 = x1 + new_w, y1 + h
            if 0 <= x1 < FRAME_WIDTH and 0 <= y1 < FRAME_HEIGHT and x2 <= FRAME_WIDTH and y2 <= FRAME_HEIGHT:
                if img_flap.shape[2] == 4:
                    alpha = img_flap[:, :, 3]/255.0
                    for c in range(3):
                        canvas[y1:y2, x1:x2, c] = alpha*img_flap[:, :, c] + (1-alpha)*canvas[y1:y2, x1:x2, c]
                else:
                    canvas[y1:y2, x1:x2] = img_flap

        # ---------------------------
        # Apply flipping
        # ---------------------------
        if FLIP_MODE is not None:
            canvas = cv2.flip(canvas, FLIP_MODE)

        # ---------------------------
        # Show fullscreen
        # ---------------------------
        cv2.imshow("Butterfly Garden", canvas)
        key = cv2.waitKey(1)
        if key == ord("q") or key == 27:
            break

cap.release