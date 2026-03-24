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
# Explosion / particle settings
# ---------------------------
COLLISION_RADIUS = 40        # hand must be this close (px) to trigger explosion
PETAL_COUNT = 14             # petals spawned per explosion
PETAL_SPEED_MIN = 2.5
PETAL_SPEED_MAX = 7.0
PETAL_LIFETIME = 55          # frames before fully transparent
PETAL_SIZE_MIN = 6
PETAL_SIZE_MAX = 14

# Petal colours: soft flower tones (BGR)
PETAL_COLORS = [
    (180, 120, 255),   # soft pink
    (200, 100, 220),   # lilac
    (80,  180, 255),   # golden yellow
    (60,  220, 255),   # warm yellow
    (160, 200, 255),   # peach
    (255, 255, 255),   # white
    (200, 150, 255),   # lavender
    (100, 240, 200),   # mint
]

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

threading.Thread(
    target=lambda: [fetch_butterflies() or time.sleep(API_FETCH_INTERVAL) for _ in iter(int, 1)],
    daemon=True
).start()

# ---------------------------
# Butterflies & particles
# ---------------------------
butterflies = []
particles = []          # flower petal particles
last_spawn_time = 0


def spawn_explosion(x, y):
    """Spawn a burst of flower petals at position (x, y)."""
    for _ in range(PETAL_COUNT):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(PETAL_SPEED_MIN, PETAL_SPEED_MAX)
        size_a = random.randint(PETAL_SIZE_MIN, PETAL_SIZE_MAX)   # long axis
        size_b = max(3, size_a // 2)                               # short axis
        particles.append({
            'x': float(x),
            'y': float(y),
            'vx': math.cos(angle) * speed,
            'vy': math.sin(angle) * speed,
            'angle': angle,          # travel direction (used for rotation)
            'color': random.choice(PETAL_COLORS),
            'size_a': size_a,
            'size_b': size_b,
            'life': PETAL_LIFETIME,  # counts down to 0
            'max_life': PETAL_LIFETIME,
            'gravity': random.uniform(0.05, 0.15),  # gentle drift down
        })


def draw_petal(canvas, p):
    """Draw one petal as a rotated filled ellipse with alpha fade."""
    alpha = p['life'] / p['max_life']
    if alpha <= 0:
        return

    cx, cy = int(p['x']), int(p['y'])
    size_a, size_b = p['size_a'], p['size_b']

    # Build a small local canvas for the petal so we can rotate it
    pad = size_a + 4
    local = np.zeros((pad * 2, pad * 2, 4), dtype=np.uint8)
    color_bgra = (*p['color'], 255)
    cv2.ellipse(
        local,
        (pad, pad),
        (size_a, size_b),
        math.degrees(p['angle']),   # rotate ellipse along travel
        0, 360,
        color_bgra,
        -1,
        cv2.LINE_AA
    )

    # Soft white centre highlight
    inner_a = max(1, size_a // 3)
    inner_b = max(1, size_b // 3)
    cv2.ellipse(local, (pad, pad), (inner_a, inner_b),
                math.degrees(p['angle']), 0, 360,
                (255, 255, 255, 180), -1, cv2.LINE_AA)

    # Place on canvas with alpha compositing
    x1, y1 = cx - pad, cy - pad
    x2, y2 = cx + pad, cy + pad

    # Clamp to canvas bounds
    lx1 = max(0, -x1)
    ly1 = max(0, -y1)
    lx2 = local.shape[1] - max(0, x2 - canvas.shape[1])
    ly2 = local.shape[0] - max(0, y2 - canvas.shape[0])
    cx1 = max(0, x1)
    cy1 = max(0, y1)
    cx2 = cx1 + (lx2 - lx1)
    cy2 = cy1 + (ly2 - ly1)

    if cx2 <= cx1 or cy2 <= cy1 or lx2 <= lx1 or ly2 <= ly1:
        return

    region = canvas[cy1:cy2, cx1:cx2]
    petal_crop = local[ly1:ly2, lx1:lx2]
    petal_alpha = (petal_crop[:, :, 3] / 255.0) * alpha

    for c in range(3):
        region[:, :, c] = (
            petal_alpha * petal_crop[:, :, c]
            + (1 - petal_alpha) * region[:, :, c]
        ).astype(np.uint8)

    canvas[cy1:cy2, cx1:cx2] = region


# ---------------------------
# Hand detection
# ---------------------------
cap = cv2.VideoCapture(0)

with mp_hands.Hands(
    static_image_mode=False,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7,
    max_num_hands=2
) as hands:

    while True:
        canvas = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        hand_points = []

        ret, frame = cap.read()
        if not ret:
            continue

        # Resize for hand detection
        h_cam, w_cam = frame.shape[:2]
        scale = FRAME_HEIGHT / h_cam
        frame_resized = cv2.resize(frame, (int(w_cam * scale), FRAME_HEIGHT))
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
        # Collision detection: hand vs butterfly → explosion
        # ---------------------------
        survived = []
        for b in butterflies:
            exploded = False
            age = time.time() - b['born']
            if age >= 5.0:          # immune during first 5 seconds
                for hx, hy in hand_points:
                    dist = math.hypot(b['x'] - hx, b['y'] - hy)
                    if dist < COLLISION_RADIUS:
                        spawn_explosion(int(b['x']), int(b['y']))
                        exploded = True
                        break
            if not exploded:
                survived.append(b)
        butterflies[:] = survived

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
                    'phase': random.uniform(0, 2 * math.pi),
                    'born': time.time()
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
            # Repulsion from hand (surviving butterflies still flee)
            for hx, hy in hand_points:
                dx = b['x'] - hx
                dy = b['y'] - hy
                dist = math.hypot(dx, dy)
                if dist < REPULSION_RADIUS and dist > 0:
                    force = (REPULSION_RADIUS - dist) / REPULSION_RADIUS * REPULSION_FORCE
                    b['vx'] += dx / dist * force
                    b['vy'] += dy / dist * force
            # Damping
            b['vx'] *= DAMPING
            b['vy'] *= DAMPING
            # Limit speed
            speed = math.hypot(b['vx'], b['vy'])
            if speed > MAX_SPEED:
                b['vx'] = (b['vx'] / speed) * MAX_SPEED
                b['vy'] = (b['vy'] / speed) * MAX_SPEED
            # Update position
            b['x'] += b['vx']
            b['y'] += b['vy']
            b['x'] = np.clip(b['x'], BUTTERFLY_SIZE // 2, FRAME_WIDTH - BUTTERFLY_SIZE // 2)
            b['y'] = np.clip(b['y'], BUTTERFLY_SIZE // 2, FRAME_HEIGHT - BUTTERFLY_SIZE // 2)

        # ---------------------------
        # Update particles
        # ---------------------------
        alive_particles = []
        for p in particles:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['vy'] += p['gravity']   # gentle gravity
            p['vx'] *= 0.97           # slight air resistance
            p['vy'] *= 0.97
            p['life'] -= 1
            if p['life'] > 0:
                alive_particles.append(p)
        particles[:] = alive_particles

        # ---------------------------
        # Draw butterflies with horizontal wing flap
        # ---------------------------
        for b in butterflies:
            img = b['img']
            h, w = img.shape[:2]
            flap = 1 + FLAP_AMPLITUDE * math.sin(2 * math.pi * FLAP_SPEED * t + b['phase'])
            new_w = max(1, int(w * flap))
            img_flap = cv2.resize(img, (new_w, h), interpolation=cv2.INTER_LINEAR)
            x1 = int(b['x'] - new_w / 2)
            y1 = int(b['y'] - h / 2)
            x2, y2 = x1 + new_w, y1 + h
            if 0 <= x1 < FRAME_WIDTH and 0 <= y1 < FRAME_HEIGHT and x2 <= FRAME_WIDTH and y2 <= FRAME_HEIGHT:
                if img_flap.shape[2] == 4:
                    alpha = img_flap[:, :, 3] / 255.0
                    for c in range(3):
                        canvas[y1:y2, x1:x2, c] = (
                            alpha * img_flap[:, :, c]
                            + (1 - alpha) * canvas[y1:y2, x1:x2, c]
                        )
                else:
                    canvas[y1:y2, x1:x2] = img_flap

        # ---------------------------
        # Draw flower petals
        # ---------------------------
        for p in particles:
            draw_petal(canvas, p)

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

cap.release()
cv2.destroyAllWindows()