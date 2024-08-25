import datetime
import json
import os
import platform
import subprocess
import tkinter as tk
import piexif
import piexif.helper
import replicate
import requests
from PIL import Image
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication

from ignoramus.upscaler import upscale_image


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
    # Get the directory of the file
    dir_path = os.path.dirname(os.path.abspath(file_path))

    # Open the directory in the file explorer based on the OS
    if platform.system() == "Windows":
        os.startfile(dir_path)
    elif platform.system() == "Darwin":  # macOS
        subprocess.Popen(["open", dir_path])
    else:  # Linux and other Unix-like
        subprocess.Popen(["xdg-open", dir_path])


def copy_image_to_clipboard(img_path):
    try:
        # Open the image using Pillow
        pil_image = Image.open(img_path)

        # Convert the image to RGB mode if it's not already
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')

        # Convert PIL image to QImage
        qimage = QImage(pil_image.tobytes(), pil_image.width, pil_image.height, QImage.Format_RGB888)

        # Create QApplication instance if it doesn't exist
        app = QApplication.instance() or QApplication([])

        # Create QPixmap from QImage
        pixmap = QPixmap.fromImage(qimage)

        # Copy to clipboard
        clipboard = app.clipboard()
        clipboard.setPixmap(pixmap)

        print(f"Image {img_path} copied to clipboard successfully.")
    except Exception as e:
        print(f"Error copying image to clipboard: {str(e)}")


def create_exif_metadata(properties, model):
    # Create a copy of properties to avoid modifying the original
    metadata = properties.copy()

    # Remove any large data fields that shouldn't be in EXIF
    metadata.pop('image', None)  # Remove the image data if present

    # Add the model information
    metadata["model"] = model

    # Convert the metadata to a JSON string
    metadata_json = json.dumps(metadata)

    # Create the EXIF dictionary
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    # Add the metadata as a UserComment
    user_comment = piexif.helper.UserComment.dump(metadata_json)
    exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment

    return exif_dict


def save_image_with_metadata(img, file_name, exif_dict):
    exif_bytes = piexif.dump(exif_dict)
    img.save(file_name, "JPEG", exif=exif_bytes, quality=95)


def fetch_and_save_image(url, file_name):
    response = requests.get(url)
    with open(file_name, "wb") as file:
        file.write(response.content)


def get_output_directory():
    if not os.path.exists("results"):
        os.makedirs("results")
    return "results"


def update_output_text(output_text, message):
    output_text.insert(tk.END, message)
    output_text.config(state="disabled")


def generate_image(model, properties):
    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    results_dir = get_output_directory()
    try:
        output = replicate.run(f"black-forest-labs/flux-{model}", input=properties)
        return output, current_time, results_dir
    except Exception:
        raise


def handle_upscaling(file_name, exif_bytes, output_text):
    update_output_text(output_text, "Upscaling image...\n")
    if upscaled_data := upscale_image(file_name):
        os.remove(file_name)
        with open(file_name, "wb") as upscaled_file:
            upscaled_file.write(upscaled_data)
        try:
            upscaled_img = Image.open(file_name)
            upscaled_img.save(file_name, "JPEG", exif=exif_bytes, quality=95)
            update_output_text(output_text, "Original image replaced with upscaled version.\n")
        except Exception as e:
            update_output_text(output_text, f"Error re-applying EXIF data: {str(e)}\n")
    else:
        update_output_text(output_text, "Error: Failed to upscale the image.\n")


def process_generated_images(output, current_time, results_dir, properties, model, output_text):
    # if output is not a list, convert it to a list
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
