import os
import tkinter as tk
from tkinter import filedialog, messagebox
import replicate
import requests
from PIL import Image
import base64
import piexif
import json


def face_swap(swap_image_path, target_image_path):
    # Convert images to base64
    with open(swap_image_path, "rb") as swap_file, open(target_image_path, "rb") as target_file:
        swap_image = base64.b64encode(swap_file.read()).decode('utf-8')
        target_image = base64.b64encode(target_file.read()).decode('utf-8')

    properties = {
        "swap_image": f"data:image/jpeg;base64,{swap_image}",
        "target_image": f"data:image/jpeg;base64,{target_image}",
        "disable_safety_checker": True
    }

    output = replicate.run(
        "omniedgeio/face-swap:1312a036be013a29527a1dffce2fbbd475fb134eb809f295859d435546d5c76b",
        input=properties,
    )

    return output


def select_swap_image():
    swap_image_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
    return swap_image_path


def create_exif_metadata(properties):
    metadata = properties.copy()
    metadata["face_swapped"] = True
    metadata_json = json.dumps(metadata)
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    user_comment = piexif.helper.UserComment.dump(metadata_json)
    exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment
    return exif_dict


def copy_exif_data(source_path, target_path):
    try:
        # Read EXIF data from source image
        with Image.open(source_path) as source_img:
            exif_data = source_img.info.get('exif')

        if exif_data:
            # Load existing EXIF data
            exif_dict = piexif.load(exif_data)
        else:
            # Create new EXIF dict if no existing data
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        # Add or update face swap information
        metadata = {"face_swapped": True}
        metadata_json = json.dumps(metadata)
        user_comment = piexif.helper.UserComment.dump(metadata_json)
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment

        # Write EXIF data to target image
        exif_bytes = piexif.dump(exif_dict)
        with Image.open(target_path) as target_img:
            target_img.save(target_path, exif=exif_bytes)

    except Exception as e:
        print(f"Error copying EXIF data: {str(e)}")


def perform_face_swap(target_image_path, output_dir):
    swap_image_path = select_swap_image()
    if not swap_image_path:
        return None

    try:
        output_url = face_swap(swap_image_path, target_image_path)

        # Download and save the face-swapped image
        response = requests.get(output_url)
        if response.status_code == 200:
            output_filename = f"face_swapped_{os.path.basename(target_image_path)}"
            output_path = os.path.join(output_dir, output_filename)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            # Copy EXIF data from the original image to the face-swapped image
            copy_exif_data(target_image_path, output_path)

            return output_path
        else:
            return None
    except Exception as e:
        print(f"Error during face swap: {str(e)}")
        return None


# This function should be called from main.py
def add_face_swap_button(button_frame, target_image_path, output_dir, refresh_gallery_callback):
    face_swap_button = tk.Button(
        button_frame,
        text="🎭 Face Swap",
        command=lambda: handle_face_swap(target_image_path, output_dir, refresh_gallery_callback)
    )
    face_swap_button.pack(side=tk.TOP, padx=5, pady=5)


def handle_face_swap(target_image_path, output_dir, refresh_gallery_callback):
    output_path = perform_face_swap(target_image_path, output_dir)
    if output_path:
        tk.messagebox.showinfo("Face Swap Complete", f"Face-swapped image saved as {os.path.basename(output_path)}")
        refresh_gallery_callback()
    else:
        tk.messagebox.showerror("Face Swap Failed", "Failed to perform face swap.")