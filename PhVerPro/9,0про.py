import cv2
import numpy as np
import os
import time

def read_image_cyrillic(file_path):
    with open(file_path, "rb") as f:
        # Читаем в цвете, чтобы не потерять контраст на желтой бумаге
        img_bgr = cv2.imdecode(np.frombuffer(f.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img_bgr is None: return None
        # Используем канал L (светлота) из LAB для чистого выделения яркости
        return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)[:, :, 0]

def write_image_cyrillic(file_path, image):
    is_success, im_buf_arr = cv2.imencode(".png", image)
    if is_success: im_buf_arr.tofile(file_path)

def process_pro_pipeline(image_path, output_path):
    img = read_image_cyrillic(image_path)
    if img is None: return False

    # Перевод в Float64 для исключения математических потерь
    img_float = img.astype(np.float64) / 255.0

    # Микро-размытие для смягчения пикселей монитора
    smoothed = cv2.GaussianBlur(img_float, (3, 3), 0.8)

    # Многомасштабное выравнивание фона (Multi-Scale Division)
    flat = np.zeros_like(img_float)
    scales = [51, 151, 301]
    
    for s in scales:
        bg = cv2.GaussianBlur(smoothed, (s, s), 0)
        flat += smoothed / (bg + 1e-8)
    
    flat /= len(scales)

    # Робастная Сигмоида без глобальной нормализации (игнорирует черные рамки)
    # Используем медиану вместо среднего, чтобы игнорировать экстремальные блики
    x0 = np.median(flat) - 0.015 
    k = 25.0 
    
    sigmoid = 1.0 / (1.0 + np.exp(-k * (flat - x0)))

    # Обрезка и возврат в 8-бит
    final = np.clip(sigmoid, 0.0, 1.0)
    final_8bit = (final * 255).astype(np.uint8)

    write_image_cyrillic(output_path, final_8bit)
    return True

raw_input = input("\nПеретащите папку с фото и нажмите ENTER:\n> ")
folder_path = raw_input.strip().strip('\'"')

if not os.path.isdir(folder_path):
    print("Ошибка пути."); exit()

image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) 
               if os.path.splitext(f)[1].lower() in {'.jpg', '.jpeg', '.png'} and not os.path.isdir(os.path.join(folder_path, f))]

if not image_files:
    print("Нет фото."); exit()

output_folder = os.path.join(folder_path, 'Processed_Pro')
os.makedirs(output_folder, exist_ok=True)

print(f"\n[ИНФО] Файлов: {len(image_files)}\n[ЛОГ] Сохранение в: {output_folder}\n" + "-"*50)

start_total = time.time()
successful = 0

for i, img_path in enumerate(image_files, 1):
    out_path = os.path.join(output_folder, os.path.splitext(os.path.basename(img_path))[0] + "_pro.png")
    print(f"[{i}/{len(image_files)}] Обработка: {os.path.basename(img_path)}...", end=" ", flush=True)
    start_time = time.time()
    
    if process_pro_pipeline(img_path, out_path):
        print(f"ОК ({time.time() - start_time:.2f}s)")
        successful += 1
    else:
        print("ОШИБКА")

print("-" * 50)
print(f"[ЛОГ] ЗАВЕРШЕНО! Успешно: {successful} / {len(image_files)}")
print(f"Затрачено: {time.time() - start_total:.2f} сек")
input("ENTER для выхода...")