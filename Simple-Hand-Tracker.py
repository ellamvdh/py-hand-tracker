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
SPAWN_INTERVAL = 1
BUTTERFLY_SIZE = 90
MAX_BUTTERFLIES = 20
MAX_CACHED_BUTTERFLIES = 15
API_URL = "https://vlinder-world.onrender.com/api/butterflies"
API_FETCH_INTERVAL = 15

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
DAISY_COUNT = 12             # daisies spawned per explosion
DAISY_SPEED_MIN = 2.5
DAISY_SPEED_MAX = 7.0
DAISY_LIFETIME = 70          # frames before fully transparent
DAISY_SIZE_MIN = 14          # radius of whole daisy
DAISY_SIZE_MAX = 26
DAISY_PETALS = 8             # petals per daisy flower

# Daisy petal colours (BGR) — white, cream, pale yellow variants
DAISY_PETAL_COLORS = [
    (255, 255, 255),   # pure white
    (210, 240, 255),   # warm white
    (180, 220, 255),   # cream
    (160, 210, 255),   # pale butter
]
# Centre colours — golden yellow tones (BGR)
DAISY_CENTER_COLORS = [
    (0,   200, 255),   # golden yellow
    (0,   180, 240),   # deep gold
    (30,  210, 255),   # amber yellow
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
    """Spawn a burst of daisy flowers at position (x, y)."""
    for _ in range(DAISY_COUNT):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(DAISY_SPEED_MIN, DAISY_SPEED_MAX)
        size = random.randint(DAISY_SIZE_MIN, DAISY_SIZE_MAX)
        spin = random.uniform(-0.12, 0.12)   # rotation per frame
        particles.append({
            'x': float(x),
            'y': float(y),
            'vx': math.cos(angle) * speed,
            'vy': math.sin(angle) * speed,
            'rotation': random.uniform(0, 2 * math.pi),  # current draw rotation
            'spin': spin,
            'petal_color': random.choice(DAISY_PETAL_COLORS),
            'center_color': random.choice(DAISY_CENTER_COLORS),
            'size': size,
            'life': DAISY_LIFETIME,
            'max_life': DAISY_LIFETIME,
            'gravity': random.uniform(0.04, 0.12),
        })


def draw_daisy(canvas, p):
    """Draw one daisy (8 oval petals around a circular centre) with alpha fade."""
    alpha = p['life'] / p['max_life']
    if alpha <= 0:
        return

    size = p['size']
    pad = size + 6
    local = np.zeros((pad * 2, pad * 2, 4), dtype=np.uint8)
    centre = (pad, pad)

    petal_color_bgra  = (*p['petal_color'],  255)
    center_color_bgra = (*p['center_color'], 255)

    petal_len = int(size * 0.82)   # half-length of each petal ellipse
    petal_w   = max(3, int(size * 0.32))  # half-width

    # Draw petals radiating outward
    for i in range(DAISY_PETALS):
        petal_angle = p['rotation'] + i * (360.0 / DAISY_PETALS)
        rad = math.radians(petal_angle)
        # Offset centre of each petal ellipse outward from flower centre
        offset = int(size * 0.45)
        px = int(centre[0] + math.cos(rad) * offset)
        py = int(centre[1] + math.sin(rad) * offset)
        cv2.ellipse(
            local, (px, py), (petal_len, petal_w),
            petal_angle, 0, 360,
            petal_color_bgra, -1, cv2.LINE_AA
        )
        # Thin darker outline on each petal for definition
        outline = (
            max(0, p['petal_color'][0] - 60),
            max(0, p['petal_color'][1] - 60),
            max(0, p['petal_color'][2] - 60),
            180
        )
        cv2.ellipse(
            local, (px, py), (petal_len, petal_w),
            petal_angle, 0, 360,
            outline, 1, cv2.LINE_AA
        )

    # Golden centre circle
    centre_r = max(4, int(size * 0.28))
    cv2.circle(local, centre, centre_r, center_color_bgra, -1, cv2.LINE_AA)
    # Darker ring around centre for depth
    dark_center = (
        max(0, p['center_color'][0] - 40),
        max(0, p['center_color'][1] - 60),
        max(0, p['center_color'][2] - 60),
        220
    )
    cv2.circle(local, centre, centre_r, dark_center, 1, cv2.LINE_AA)
    # Small bright highlight dot
    cv2.circle(local, (centre[0] - centre_r//3, centre[1] - centre_r//3),
               max(1, centre_r // 3), (255, 255, 255, 180), -1, cv2.LINE_AA)

    # Composite onto canvas with alpha fade
    cx, cy = int(p['x']), int(p['y'])
    x1, y1 = cx - pad, cy - pad
    x2, y2 = cx + pad, cy + pad

    lx1 = max(0, -x1);  ly1 = max(0, -y1)
    lx2 = local.shape[1] - max(0, x2 - canvas.shape[1])
    ly2 = local.shape[0] - max(0, y2 - canvas.shape[0])
    cx1 = max(0, x1);   cy1 = max(0, y1)
    cx2 = cx1 + (lx2 - lx1)
    cy2 = cy1 + (ly2 - ly1)

    if cx2 <= cx1 or cy2 <= cy1 or lx2 <= lx1 or ly2 <= ly1:
        return

    region     = canvas[cy1:cy2, cx1:cx2]
    daisy_crop = local[ly1:ly2, lx1:lx2]
    a = (daisy_crop[:, :, 3] / 255.0) * alpha

    for c in range(3):
        region[:, :, c] = (a * daisy_crop[:, :, c] + (1 - a) * region[:, :, c]).astype(np.uint8)
    canvas[cy1:cy2, cx1:cx2] = region


# ---------------------------
# Background: dark green garden
# ---------------------------
def build_background(w, h):
    """
    Generate a lush dark-green garden background once at startup.
    Layers: deep gradient → scattered bokeh glows → leaf shapes → vignette.
    """
    bg = np.zeros((h, w, 3), dtype=np.uint8)

    # --- Base gradient: very dark green top → slightly lighter bottom ---
    for y in range(h):
        t = y / h
        r = int(4  + t * 8)
        g = int(28 + t * 28)
        b = int(10 + t * 14)
        bg[y, :] = (b, g, r)

    # --- Soft bokeh glows (out-of-focus light spots) ---
    rng = np.random.default_rng(42)
    for _ in range(60):
        cx = int(rng.uniform(0, w))
        cy = int(rng.uniform(0, h))
        radius = int(rng.uniform(30, 120))
        brightness = rng.uniform(0.04, 0.18)
        # Draw a soft circle by blending
        y1c = max(0, cy - radius); y2c = min(h, cy + radius)
        x1c = max(0, cx - radius); x2c = min(w, cx + radius)
        ys, xs = np.ogrid[y1c:y2c, x1c:x2c]
        dist = np.sqrt((xs - cx)**2 + (ys - cy)**2)
        mask = np.clip(1 - dist / radius, 0, 1) * brightness
        for c, gain in enumerate([0, 1, 0]):   # green-tinted glow
            bg[y1c:y2c, x1c:x2c, c] = np.clip(
                bg[y1c:y2c, x1c:x2c, c] + mask * gain * 120, 0, 255
            ).astype(np.uint8)
        # Also add a slight warm highlight in the centre
        for c, gain in enumerate([0.2, 0.9, 0.3]):
            bg[y1c:y2c, x1c:x2c, c] = np.clip(
                bg[y1c:y2c, x1c:x2c, c] + mask * 0.4 * gain * 80, 0, 255
            ).astype(np.uint8)

    # --- Leaf shapes ---
    def draw_leaf(img, tip, base, width_frac, color_dark, color_light):
        """Draw a single elongated leaf as a filled polygon with a vein."""
        tx, ty = tip
        bx, by = base
        dx, dy = tx - bx, ty - by
        length = math.hypot(dx, dy)
        if length < 1:
            return
        nx, ny = -dy / length, dx / length   # normal
        half = length * width_frac
        mid_x = (tx + bx) / 2 + nx * half * 0.3
        mid_y = (ty + by) / 2 + ny * half * 0.3
        pts = np.array([
            [bx, by],
            [int(mid_x + nx * half), int(mid_y + ny * half)],
            [tx, ty],
            [int(mid_x - nx * half), int(mid_y - ny * half)],
        ], dtype=np.int32)
        cv2.fillPoly(img, [pts], color_dark)
        # Central vein
        cv2.line(img, (bx, by), (tx, ty), color_light, 1, cv2.LINE_AA)

    leaf_configs = [
        # (count, size_range, color_dark_BGR, color_light_BGR, y_band)
        (80,  (80,  220), (10, 55, 8),   (20, 90, 15),  (0.0, 1.0)),   # mid leaves
        (50,  (120, 320), (6,  38, 5),   (12, 68, 10),  (0.3, 1.0)),   # big background leaves
        (60,  (40,  100), (15, 75, 12),  (30, 110, 20), (0.0, 0.7)),   # small bright leaves
    ]
    for count, (smin, smax), cdark, clight, (ylo, yhi) in leaf_configs:
        for _ in range(count):
            bx = int(rng.uniform(0, w))
            by = int(rng.uniform(ylo * h, yhi * h))
            angle = rng.uniform(0, 2 * math.pi)
            length = int(rng.uniform(smin, smax))
            tx = int(bx + math.cos(angle) * length)
            ty = int(by + math.sin(angle) * length)
            width_frac = rng.uniform(0.12, 0.26)
            draw_leaf(bg, (tx, ty), (bx, by), width_frac, cdark, clight)

    # --- Subtle blur to blend everything softly ---
    bg = cv2.GaussianBlur(bg, (7, 7), 0)

    # --- Re-draw a sharper layer of foreground leaves on top ---
    for _ in range(35):
        bx = int(rng.uniform(-40, w + 40))
        by = int(rng.uniform(int(h * 0.5), h + 40))
        angle = rng.uniform(-math.pi * 0.6, math.pi * 0.6) - math.pi / 2
        length = int(rng.uniform(140, 380))
        tx = int(bx + math.cos(angle) * length)
        ty = int(by + math.sin(angle) * length)
        draw_leaf(bg, (tx, ty), (bx, by), rng.uniform(0.10, 0.22),
                  (8, 45, 6), (18, 80, 12))

    # --- Vignette: darken edges ---
    ys, xs = np.ogrid[:h, :w]
    cx_v, cy_v = w / 2, h / 2
    dist_v = np.sqrt(((xs - cx_v) / (w / 2))**2 + ((ys - cy_v) / (h / 2))**2)
    vignette = np.clip(1 - dist_v * 0.55, 0.35, 1.0)
    for c in range(3):
        bg[:, :, c] = (bg[:, :, c] * vignette).astype(np.uint8)

    return bg

BACKGROUND = build_background(FRAME_WIDTH, FRAME_HEIGHT)

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
        canvas = BACKGROUND.copy()
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
            if age >= 1.5:          # immune during first 5 seconds
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
            p['rotation'] += math.degrees(p['spin'])  # spin the daisy
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
        # Draw daisy particles
        # ---------------------------
        for p in particles:
            draw_daisy(canvas, p)

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