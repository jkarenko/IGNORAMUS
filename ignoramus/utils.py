import json
import os
import platform
import subprocess
import tkinter as tk
import piexif
import piexif.helper
from PIL import Image
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication

from ignoramus.image_generator import fetch_and_save_image, create_exif_metadata, save_image_with_metadata, \
    handle_upscaling


def initialize_app():
    if 'REPLICATE_API_TOKEN' in os.environ:
        print("Replicate API token loaded from environment variable.")
        return

    token_file = './token.txt'
    if os.path.exists(token_file):
        with open(token_file, 'r') as file:
            api_token = file.read().strip()
        os.environ['REPLICATE_API_TOKEN'] = api_token
        print("Replicate API token loaded from token.txt and set in environment variables.")
    else:
        print(
            f"ERROR: REPLICATE_API_TOKEN not set and {token_file} not found. Please set the environment variable or create {token_file} with your Replicate API token.")


def focus_next_widget(event):
    event.widget.tk_focusNext().focus()
    return "break"


def focus_previous_widget(event):
    event.widget.tk_focusPrev().focus()
    return "break"


def read_image_metadata(file_path):
    try:
        exif_dict = piexif.load(file_path)
        user_comment = exif_dict["Exif"][piexif.ExifIFD.UserComment]
        metadata = piexif.helper.UserComment.load(user_comment)
        return json.loads(metadata)
    except (KeyError, json.JSONDecodeError):
        return None


def open_file_location(file_path):
    dir_path = os.path.dirname(os.path.abspath(file_path))
    if platform.system() == "Windows":
        os.startfile(dir_path)
    elif platform.system() == "Darwin":  # macOS
        subprocess.Popen(["open", dir_path])
    else:  # Linux and other Unix-like
        subprocess.Popen(["xdg-open", dir_path])


def copy_image_to_clipboard(img_path):
    try:
        pil_image = Image.open(img_path)
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        qimage = QImage(pil_image.tobytes(), pil_image.width, pil_image.height, QImage.Format_RGB888)
        app = QApplication.instance() or QApplication([])
        pixmap = QPixmap.fromImage(qimage)
        clipboard = app.clipboard()
        clipboard.setPixmap(pixmap)

        print(f"Image {img_path} copied to clipboard successfully.")
    except Exception as e:
        print(f"Error copying image to clipboard: {str(e)}")


def update_output_text(output_text, message):
    output_text.insert(tk.END, message)
    output_text.config(state="disabled")


def process_generated_images(output, current_time, results_dir, properties, model, output_text):
    if not isinstance(output, list):
        output = [output]
    for idx, url in enumerate(output):
        file_name = f"{results_dir}/img_{current_time}{f'_{str(idx)}' if len(output) > 1 else ''}.jpg"
        fetch_and_save_image(url, file_name)
        img = Image.open(file_name)
        exif_dict = create_exif_metadata(properties, model)
        save_image_with_metadata(img, file_name, exif_dict)
        update_output_text(output_text, "Saved image with metadata in EXIF.\n")
        if properties.get("upscale", False):
            handle_upscaling(file_name, piexif.dump(exif_dict), output_text)
        else:
            update_output_text(output_text, "Upscaling skipped.\n")
