import mediapipe as mp
import cv2
import numpy as np
import time
import math
#added to github 
# MediaPipe setup
mp_drawing = mp.solutions.drawing_utils
mp_hands = mp.solutions.hands

# Video capture
cap = cv2.VideoCapture(0)

# Time tracking
last_circle_time = time.time()
circle_interval = 3  # seconds

# Store persistent circles
circles = []

# Circle properties
CIRCLE_RADIUS = 30
CIRCLE_COLOR = (0, 0, 255)  # red
MOVE_SPEED = 5  # pixels per frame

# Hand detection setup
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

        # Resize frame
        frame = cv2.resize(frame, (640, 480))

        # Process with MediaPipe
        results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        # Black canvas
        canvas = np.zeros((480, 640, 3), dtype=np.uint8)

        hand_landmarks_list = []

        # Draw hand landmarks and store all landmark positions
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(canvas, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                for landmark in hand_landmarks.landmark:
                    x_pixel = int(landmark.x * 640)
                    y_pixel = int(landmark.y * 480)
                    hand_landmarks_list.append((x_pixel, y_pixel))

        # Spawn new circle every 10 seconds at index finger tip
        current_time = time.time()
        if results.multi_hand_landmarks and (current_time - last_circle_time >= circle_interval):
            # Use first hand's index finger tip
            landmark = results.multi_hand_landmarks[0].landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            x_pixel = int(landmark.x * 640)
            y_pixel = int(landmark.y * 480)

            # Prevent overlap on spawn
            safe_to_add = True
            for circle in circles:
                dist = math.hypot(circle['x'] - x_pixel, circle['y'] - y_pixel)
                if dist < 2 * CIRCLE_RADIUS:
                    safe_to_add = False
                    break
            if safe_to_add:
                circles.append({'x': x_pixel, 'y': y_pixel})
                last_circle_time = current_time

        # Move circles away if any hand landmark is over them
        for circle in circles:
            for hx, hy in hand_landmarks_list:
                dx = circle['x'] - hx
                dy = circle['y'] - hy
                distance = math.hypot(dx, dy)
                if distance < CIRCLE_RADIUS:
                    if distance == 0:
                        dx, dy = 1, 0
                        distance = 1
                    # move away smoothly
                    circle['x'] += int(dx / distance * MOVE_SPEED)
                    circle['y'] += int(dy / distance * MOVE_SPEED)
                    # Keep inside canvas
                    circle['x'] = np.clip(circle['x'], CIRCLE_RADIUS, 640 - CIRCLE_RADIUS)
                    circle['y'] = np.clip(circle['y'], CIRCLE_RADIUS, 480 - CIRCLE_RADIUS)

        # Draw all circles
        for circle in circles:
            cv2.circle(canvas, (circle['x'], circle['y']), CIRCLE_RADIUS, CIRCLE_COLOR, -1)

        # Show canvas
        cv2.imshow("Butterfly Garden", canvas)

        # Exit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()