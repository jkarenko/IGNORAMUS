import datetime
import json
import os

import piexif
import piexif.helper
import replicate
import requests
from PIL import Image

from ignoramus.upscaler import upscale_image


def generate_image(model, properties):
    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    results_dir = get_output_directory()
    try:
        output = replicate.run(f"black-forest-labs/flux-{model}", input=properties)
        return output, current_time, results_dir
    except Exception:
        raise


def get_output_directory():
    if not os.path.exists("results"):
        os.makedirs("results")
    return "results"


def create_exif_metadata(properties, model):
    metadata = properties.copy()
    metadata.pop('image', None)
    metadata["model"] = model
    metadata_json = json.dumps(metadata)
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
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


def handle_upscaling(file_name, exif_bytes):
    if upscaled_data := upscale_image(file_name):
        os.remove(file_name)
        with open(file_name, "wb") as upscaled_file:
            upscaled_file.write(upscaled_data)
        try:
            upscaled_img = Image.open(file_name)
            upscaled_img.save(file_name, "JPEG", exif=exif_bytes, quality=95)
            return True
        except Exception:
            return False
    return False


def process_generated_images(output, current_time, results_dir, properties, model):
    if not isinstance(output, list):
        output = [output]
    processed_images = []
    for idx, url in enumerate(output):
        file_name = f"{results_dir}/img_{current_time}{f'_{str(idx)}' if len(output) > 1 else ''}.jpg"
        fetch_and_save_image(url, file_name)
        img = Image.open(file_name)
        exif_dict = create_exif_metadata(properties, model)
        save_image_with_metadata(img, file_name, exif_dict)
        if properties.get("upscale", False):
            upscaled = handle_upscaling(file_name, piexif.dump(exif_dict))
        else:
            upscaled = False
        processed_images.append({"file_name": file_name, "upscaled": upscaled})
    return processed_images
