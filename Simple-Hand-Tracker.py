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
import ctypes

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
TARGET_FPS = 60  # Render FPS (onafhankelijk van hand tracking)

# Physics
REPULSION_RADIUS = 120
REPULSION_FORCE = 1.8
DAMPING = 0.95
WANDER_STRENGTH = 0.5
MAX_SPEED = 8

# Boundary repulsion
BOUNDARY_REPULSION_RADIUS = 100  # Onzichtbare zone aan de randen
BOUNDARY_REPULSION_FORCE = 2.0   # Kracht waarmee vlinders teruggeduwd worden

# Wing flap
FLAP_AMPLITUDE = 0.25
FLAP_SPEED = 3.0

# Image flip mode: 0=verticaal, 1=horizontaal, -1=beide
FLIP_MODE = 1

# ---------------------------
# Explosion / particle settings
# ---------------------------
COLLISION_RADIUS = 40
DAISY_COUNT = 3
DAISY_SPEED_MIN = 2.5
DAISY_SPEED_MAX = 7.0
DAISY_LIFETIME = 20
DAISY_SIZE_MIN = 70
DAISY_SIZE_MAX = 90

# ---------------------------
# Load daisy image
# ---------------------------
_daisy_src = cv2.imread("daisy.png", cv2.IMREAD_UNCHANGED)
if _daisy_src is None:
    raise FileNotFoundError(
        "daisy.png not found. Place daisy.png in the same directory as this script."
    )
# Ensure the image has an alpha channel
if _daisy_src.shape[2] == 3:
    _daisy_src = cv2.cvtColor(_daisy_src, cv2.COLOR_BGR2BGRA)

def _get_daisy_image(size: int) -> np.ndarray:
    """Return daisy.png resized to (size x size), with alpha channel."""
    return cv2.resize(_daisy_src, (size, size), interpolation=cv2.INTER_AREA)

# ---------------------------
# Idle prompt settings
# ---------------------------
IDLE_TIMEOUT = 3.0     # seconds without hands before prompt appears
PROMPT_TEXT  = "Breng je handen in beeld om vlinders op te roepen!"
PROMPT_FADE  = 0.025   # alpha step per frame

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
particles   = []
last_spawn_time = 0


def spawn_explosion(x, y):
    for _ in range(DAISY_COUNT):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(DAISY_SPEED_MIN, DAISY_SPEED_MAX)
        size  = random.randint(DAISY_SIZE_MIN, DAISY_SIZE_MAX)
        spin  = random.uniform(-0.12, 0.12)
        particles.append({
            'x': float(x), 'y': float(y),
            'vx': math.cos(angle) * speed,
            'vy': math.sin(angle) * speed,
            'rotation': random.uniform(0, 360),   # degrees, for cv2.getRotationMatrix2D
            'spin': spin,                           # radians/frame, converted to degrees on update
            'size': size,
            'life': DAISY_LIFETIME,
            'max_life': DAISY_LIFETIME,
            'gravity': random.uniform(0.04, 0.12),
            'img': _get_daisy_image(size),          # pre-scaled daisy image for this particle
        })


def draw_daisy(canvas, p):
    """Blit the daisy image onto the canvas, rotated and faded according to particle state."""
    alpha_frac = p['life'] / p['max_life']
    if alpha_frac <= 0:
        return

    img  = p['img']                    # BGRA, already the right size
    size = img.shape[0]                # square
    half = size // 2

    # --- Rotate the daisy sprite ---
    M        = cv2.getRotationMatrix2D((half, half), p['rotation'], 1.0)
    rotated  = cv2.warpAffine(img, M, (size, size), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

    # --- Compute canvas region ---
    cx, cy = int(p['x']), int(p['y'])
    x1, y1 = cx - half, cy - half
    x2, y2 = x1 + size, y1 + size

    # Clip to canvas bounds
    lx1 = max(0, -x1);  ly1 = max(0, -y1)
    lx2 = size - max(0, x2 - canvas.shape[1])
    ly2 = size - max(0, y2 - canvas.shape[0])
    cx1 = max(0, x1);   cy1 = max(0, y1)
    cx2 = cx1 + (lx2 - lx1)
    cy2 = cy1 + (ly2 - ly1)

    if cx2 <= cx1 or cy2 <= cy1 or lx2 <= lx1 or ly2 <= ly1:
        return

    region      = canvas[cy1:cy2, cx1:cx2]
    daisy_crop  = rotated[ly1:ly2, lx1:lx2]

    # Combine sprite alpha with fade
    a = (daisy_crop[:, :, 3] / 255.0) * alpha_frac
    for c in range(3):
        region[:, :, c] = (
            a * daisy_crop[:, :, c] + (1 - a) * region[:, :, c]
        ).astype(np.uint8)

    canvas[cy1:cy2, cx1:cx2] = region



# ---------------------------
# Background: Load image file
# ---------------------------
def build_background(w, h):
    """
    Loads background.png and resizes it to screen size.
    Supports transparency and safe fallback.
    """
    path = "background.png"  # change if needed

    bg = cv2.imread(path, cv2.IMREAD_UNCHANGED)

    if bg is None:
        print("⚠️ background.png not found, using fallback color")
        bg = np.zeros((h, w, 3), dtype=np.uint8)
        bg[:] = (15, 45, 10)
        return bg

    # If image has alpha channel → remove it (since you're not using it here)
    if bg.shape[2] == 4:
        bg = cv2.cvtColor(bg, cv2.COLOR_BGRA2BGR)

    # Resize to fit screen
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_AREA)

    return bg


# Build once (important: NOT inside loop)
BACKGROUND = build_background(FRAME_WIDTH, FRAME_HEIGHT)

# ---------------------------
# Hand detection
# ---------------------------
cap = cv2.VideoCapture(0)

# Hide cursor on start (Windows & Linux compatible)
def hide_cursor():
    try:
        # Windows
        ctypes.windll.user32.ShowCursor(False)
    except:
        try:
            # Linux/Raspberry Pi - use xdotool
            import subprocess
            subprocess.run(['unclutter', '-display', ':0', '-noevents', '-grab'], 
                         start_new_session=True, stderr=subprocess.DEVNULL)
        except:
            pass  # Cursor hiding not available on this system

def show_cursor():
    try:
        ctypes.windll.user32.ShowCursor(True)
    except:
        pass

# ---------------------------
# Hand tracking thread
# ---------------------------
hand_tracking_lock = threading.Lock()
latest_hand_data = {'landmarks': None, 'frame_width': FRAME_WIDTH}
hand_tracking_stop = False

def hand_tracking_thread():
    """Voert hand tracking uit in een aparte thread."""
    global latest_hand_data, hand_tracking_stop
    
    with mp_hands.Hands(
        static_image_mode=False,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        max_num_hands=2
    ) as hands:
        while not hand_tracking_stop:
            try:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.001)
                    continue
                
                h_cam, w_cam = frame.shape[:2]
                scale = FRAME_HEIGHT / h_cam
                frame_width = int(w_cam * scale)
                frame_resized = cv2.resize(frame, (frame_width, FRAME_HEIGHT))
                frame_resized = cv2.flip(frame_resized, -1)  # Draai camera 180 graden
                rgb_frame = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb_frame)
                
                # Thread-safe update van hand landmarks
                with hand_tracking_lock:
                    latest_hand_data['landmarks'] = results
                    latest_hand_data['frame_width'] = frame_width
            except Exception as e:
                print(f"Hand tracking error: {e}")
                time.sleep(0.1)

# Idle prompt state
last_hand_time = time.time()
prompt_alpha   = 0.0

hide_cursor()  # Hide cursor on start

tracker_thread = None  # Will be set in try block

try:
    # Start hand tracking thread
    tracker_thread = threading.Thread(target=hand_tracking_thread, daemon=True)
    tracker_thread.start()
    
    # Main render loop
    frame_time = 1.0 / TARGET_FPS
    last_frame_time = time.time()
    
    while True:
        try:
            # Frame rate control
            now = time.time()
            time_since_last_frame = now - last_frame_time
            if time_since_last_frame < frame_time:
                time.sleep(frame_time - time_since_last_frame)
            last_frame_time = time.time()
            
            canvas      = BACKGROUND.copy()
            hand_points = []
            
            # Get latest hand landmarks from tracking thread
            with hand_tracking_lock:
                hand_data = latest_hand_data.copy()
            
            results = hand_data['landmarks']
            frame_width = hand_data['frame_width']
            
            if results is not None and results.multi_hand_landmarks:
                last_hand_time = time.time()   # reset idle clock
                for hand_landmarks in results.multi_hand_landmarks:
                    # Sla alle hand landmarks op voor later gebruik
                    landmarks_xy = []
                    for lm in hand_landmarks.landmark:
                        x = int(lm.x * frame_width)
                        y = int(lm.y * FRAME_HEIGHT)
                        hand_points.append((x, y))
                        landmarks_xy.append((x, y))
                    
                    # Teken alle connections handmatig
                    for connection in mp_hands.HAND_CONNECTIONS:
                        start_idx, end_idx = connection
                        if start_idx < len(landmarks_xy) and end_idx < len(landmarks_xy):
                            pt1 = landmarks_xy[start_idx]
                            pt2 = landmarks_xy[end_idx]
                            cv2.line(canvas, pt1, pt2, (75, 100, 130), 30)
                    
                    # Teken gevulde cirkels op alle landmarks zonder randjes
                    for lm in hand_landmarks.landmark:
                        x = int(lm.x * frame_width)
                        y = int(lm.y * FRAME_HEIGHT)
                        cv2.circle(canvas, (x, y), 15, (75, 100, 130), -1)
                    
                    # Teken een lijn tussen punt 5 (wijsvinger MCP) en punt 2 (duim PIP)
                    if len(landmarks_xy) >= 6:
                        pt5 = landmarks_xy[5]
                        pt2 = landmarks_xy[2]
                        cv2.line(canvas, pt5, pt2, (75, 100, 130), 30)
                    
                    # Vul het stuk tussen punten 0, 1, 2, 5, 9, 13, 17 in met huidskleur
                    fill_points = []
                    for idx in [0, 1, 2, 5, 9, 13, 17]:
                        if idx < len(landmarks_xy):
                            fill_points.append(landmarks_xy[idx])
                    
                    if len(fill_points) >= 3:
                        points_array = np.array(fill_points, dtype=np.int32)
                        # Dezelfde kleur als de rest
                        cv2.fillPoly(canvas, [points_array], (75, 100, 130))

            # ---------------------------
            # Collision detection
            # ---------------------------
            survived = []
            for b in butterflies:
                exploded = False
                age = time.time() - b['born']
                if age >= 1.0:
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
            if current_time - last_spawn_time > SPAWN_INTERVAL and butterfly_images:
                # Bepaal spawnpunt: bij hand als aanwezig, anders willekeurig
                if results is not None and results.multi_hand_landmarks:
                    lm = results.multi_hand_landmarks[0].landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                    x = int(lm.x * FRAME_WIDTH)
                    y = int(lm.y * FRAME_HEIGHT)
                else:
                    # Willekeurig punt in het scherm
                    x = random.randint(100, FRAME_WIDTH - 100)
                    y = random.randint(100, FRAME_HEIGHT - 100)
                
                # Spawn vlinder
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
                b['vx'] += random.uniform(-1.0, 1.0)
                b['vy'] += random.uniform(-1.0, 1.0)
                for hx, hy in hand_points:
                    dx   = b['x'] - hx
                    dy   = b['y'] - hy
                    dist = math.hypot(dx, dy)
                    if dist < REPULSION_RADIUS and dist > 0:
                        force = (REPULSION_RADIUS - dist) / REPULSION_RADIUS * REPULSION_FORCE
                        b['vx'] += dx / dist * force
                        b['vy'] += dy / dist * force
                
                # Boundary repulsion - duw vlinders weg van de randen
                # Links
                if b['x'] < BOUNDARY_REPULSION_RADIUS:
                    dist_to_edge = b['x']
                    force = (BOUNDARY_REPULSION_RADIUS - dist_to_edge) / BOUNDARY_REPULSION_RADIUS * BOUNDARY_REPULSION_FORCE
                    b['vx'] += force
                # Rechts
                if b['x'] > FRAME_WIDTH - BOUNDARY_REPULSION_RADIUS:
                    dist_to_edge = FRAME_WIDTH - b['x']
                    force = (BOUNDARY_REPULSION_RADIUS - dist_to_edge) / BOUNDARY_REPULSION_RADIUS * BOUNDARY_REPULSION_FORCE
                    b['vx'] -= force
                # Boven
                if b['y'] < BOUNDARY_REPULSION_RADIUS:
                    dist_to_edge = b['y']
                    force = (BOUNDARY_REPULSION_RADIUS - dist_to_edge) / BOUNDARY_REPULSION_RADIUS * BOUNDARY_REPULSION_FORCE
                    b['vy'] += force
                # Onder
                if b['y'] > FRAME_HEIGHT - BOUNDARY_REPULSION_RADIUS:
                    dist_to_edge = FRAME_HEIGHT - b['y']
                    force = (BOUNDARY_REPULSION_RADIUS - dist_to_edge) / BOUNDARY_REPULSION_RADIUS * BOUNDARY_REPULSION_FORCE
                    b['vy'] -= force
                
                b['vx'] *= DAMPING
                b['vy'] *= DAMPING
                speed = math.hypot(b['vx'], b['vy'])
                if speed > MAX_SPEED:
                    b['vx'] = (b['vx'] / speed) * MAX_SPEED
                    b['vy'] = (b['vy'] / speed) * MAX_SPEED
                b['x'] += b['vx']
                b['y'] += b['vy']
                # Zachte clip als absolute veiligheid (vlinders mogen niet echt uit het scherm)
                b['x'] = np.clip(b['x'], 0, FRAME_WIDTH)
                b['y'] = np.clip(b['y'], 0, FRAME_HEIGHT)

            # ---------------------------
            # Update particles
            # ---------------------------
            alive_particles = []
            for p in particles:
                p['x']        += p['vx']
                p['y']        += p['vy']
                p['vy']       += p['gravity']
                p['vx']       *= 0.97
                p['vy']       *= 0.97
                p['rotation'] += math.degrees(p['spin'])
                p['life']     -= 1
                if p['life'] > 0:
                    alive_particles.append(p)
            particles[:] = alive_particles

            # ---------------------------
            # Draw butterflies
            # ---------------------------
            for b in butterflies:
                img   = b['img']
                h, w  = img.shape[:2]
                flap  = 1 + FLAP_AMPLITUDE * math.sin(2 * math.pi * FLAP_SPEED * t + b['phase'])
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
            # Idle prompt: update alpha
            # ---------------------------
            if time.time() - last_hand_time > IDLE_TIMEOUT:
                prompt_alpha = min(1.0, prompt_alpha + PROMPT_FADE)
            else:
                prompt_alpha = max(0.0, prompt_alpha - PROMPT_FADE * 2)

            # ---------------------------
            # Apply flipping
            # ---------------------------
            if FLIP_MODE is not None:
                canvas = cv2.flip(canvas, FLIP_MODE)

            # ---------------------------
            # Draw prompt AFTER flip so text is not mirrored
            # ---------------------------
            if prompt_alpha > 0.01:
                font          = cv2.FONT_HERSHEY_SIMPLEX
                font_scale    = FRAME_WIDTH / 1800
                thickness_txt = max(1, int(FRAME_WIDTH / 900))
                (tw, th), _   = cv2.getTextSize(PROMPT_TEXT, font, font_scale, thickness_txt)
                tx = (FRAME_WIDTH  - tw) // 2
                ty = int(FRAME_HEIGHT * 0.82)
                # Drop shadow
                shadow = canvas.copy()
                cv2.putText(shadow, PROMPT_TEXT, (tx + 2, ty + 2),
                            font, font_scale, (0, 0, 0), thickness_txt + 2, cv2.LINE_AA)
                cv2.addWeighted(shadow, prompt_alpha * 0.6, canvas, 1 - prompt_alpha * 0.6, 0, canvas)
                # Main text — soft green-white to match the garden
                text_layer = canvas.copy()
                cv2.putText(text_layer, PROMPT_TEXT, (tx, ty),
                            font, font_scale, (200, 240, 210), thickness_txt, cv2.LINE_AA)
                cv2.addWeighted(text_layer, prompt_alpha, canvas, 1 - prompt_alpha, 0, canvas)

            cv2.imshow("Butterfly Garden", canvas)
            key = cv2.waitKey(1)
            if key == ord("q") or key == 27:
                break
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(0.1)  # Prevent rapid error spam
            continue

except Exception as e:
    print(f"Fatal error: {e}")
finally:
    # Stop hand tracking thread
    hand_tracking_stop = True
    if tracker_thread is not None:
        tracker_thread.join(timeout=2)
    
    # Restore cursor and cleanup
    show_cursor()
    cap.release()
    cv2.destroyAllWindows()