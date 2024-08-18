import base64
import datetime
import json
import os
import platform
import random
import subprocess
import threading
import time
import tkinter as tk
from time import perf_counter
from tkinter import ttk, filedialog

import piexif
import piexif.helper
import replicate
import requests
from PIL import Image
from PIL import ImageTk
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication

from ignoramus.upscaler import upscale_image
from ignoramus.version_checker import get_current_version, check_latest_version, update_application, restart_application


def focus_previous_widget(event):
    event.widget.tk_focusPrev().focus()
    return "break"


def focus_next_widget(event):
    event.widget.tk_focusNext().focus()
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


class ImageGeneratorGUI:
    def __init__(self, master):
        self.generate_frame = None
        self.sliders = None
        self.full_size_image = None
        self.gallery_tab = None
        self.gallery_notebook = None
        self.on_frame_configure = None
        self.gallery_images_frame = None
        self.gallery_scrollbar = None
        self.gallery_canvas = None
        self.gallery_frame = None
        self.step_values = None
        self.default_values = None
        self.default_values_dev = None
        self.output_text = None
        self.generate_button = None
        self.param_frame = None
        self.prompt_text = None
        self.model_combo = None
        self.model_var = None
        self.is_generating = False
        self.progress_bar = None
        self.master = master
        master.title("IGNORAMUS")
        master.geometry("1200x900")

        self.common_vars = {}
        self.model_specific_vars = {
            "pro": {},
            "dev": {},
            "schnell": {}
        }

        self.create_widgets()
        self.setup_keyboard_shortcuts()
        self.create_gallery()

    def create_widgets(self):
        # Create a main frame to hold everything
        main_frame = ttk.Frame(self.master)
        main_frame.pack(side=tk.TOP, expand=False)

        # Create left frame for controls
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, expand=False)

        # Model selection
        ttk.Label(left_frame, text="Select Model:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.model_var = tk.StringVar(value="pro")
        self.model_combo = ttk.Combobox(left_frame, textvariable=self.model_var, values=["pro", "dev", "schnell"],
                                        state="readonly")
        self.model_combo.grid(row=0, column=1, padx=10, pady=10, sticky="we")
        self.model_combo.bind("<<ComboboxSelected>>", self.update_parameter_fields)

        # Common parameters
        ttk.Label(left_frame, text="Prompt:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.prompt_text = tk.Text(left_frame, height=4, width=50)
        self.prompt_text.grid(row=1, column=1, padx=10, pady=10, sticky="we")

        # Model-specific parameters
        self.param_frame = ttk.Frame(left_frame)
        self.param_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="we")

        # Frame for Generate button and progress bar
        self.generate_frame = ttk.Frame(left_frame)
        self.generate_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="we")

        # Generate button
        self.generate_button = ttk.Button(self.generate_frame, text="Generate Image", command=self.generate_image)
        self.generate_button.pack(fill=tk.X)

        # Progress bar (initially hidden)
        self.progress_bar = ttk.Progressbar(self.generate_frame, mode='indeterminate',
                                            style="red.Horizontal.TProgressbar")

        # Output
        self.output_text = tk.Text(left_frame, height=20, width=70, state="disabled")
        self.output_text.grid(row=4, column=0, columnspan=2, padx=10, pady=10)

        self.initialize_variables()
        self.update_parameter_fields()

        # Create right frame for gallery
        self.gallery_frame = ttk.Frame(main_frame)
        self.gallery_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def initialize_variables(self):
        self.common_vars = {
            "aspect_ratio": tk.StringVar(value="16:9"),
            "upscale": tk.BooleanVar(value=False),
            "seed": tk.IntVar(value=random.randint(0, 2 ** 32 - 1)),
            "randomize_seed": tk.BooleanVar(value=True),
        }

        self.default_values = {
            "pro": {
                "steps": 25,
                "guidance": 3.0,
                "interval": 2.0,
                "safety_tolerance": 5,
            },
            "dev": {
                "guidance": 3.5,
                "num_outputs": 1,
                "output_quality": 80,
                "prompt_strength": 0.8,
                "num_inference_steps": 50,
                "output_format": "jpg",
                "disable_safety_checker": True,
            },
            "schnell": {
                "num_outputs": 1,
                "output_quality": 80,
                "output_format": "jpg",
                "disable_safety_checker": True,
            }
        }

        self.model_specific_vars = {
            "pro": {
                "steps": tk.IntVar(value=self.default_values["pro"]["steps"]),
                "guidance": tk.DoubleVar(value=self.default_values["pro"]["guidance"]),
                "interval": tk.DoubleVar(value=self.default_values["pro"]["interval"]),
                "safety_tolerance": tk.IntVar(value=self.default_values["pro"]["safety_tolerance"]),
            },
            "dev": {
                "image_path": tk.StringVar(),
                "guidance": tk.DoubleVar(value=self.default_values["dev"]["guidance"]),
                "num_outputs": tk.IntVar(value=self.default_values["dev"]["num_outputs"]),
                "output_format": tk.StringVar(value=self.default_values["dev"]["output_format"]),
                "output_quality": tk.IntVar(value=self.default_values["dev"]["output_quality"]),
                "prompt_strength": tk.DoubleVar(value=self.default_values["dev"]["prompt_strength"]),
                "num_inference_steps": tk.IntVar(value=self.default_values["dev"]["num_inference_steps"]),
                "disable_safety_checker": tk.BooleanVar(value=self.default_values["dev"]["disable_safety_checker"]),
            },
            "schnell": {
                "num_outputs": tk.IntVar(value=self.default_values["schnell"]["num_outputs"]),
                "output_format": tk.StringVar(value=self.default_values["schnell"]["output_format"]),
                "output_quality": tk.IntVar(value=self.default_values["schnell"]["output_quality"]),
                "disable_safety_checker": tk.BooleanVar(value=self.default_values["schnell"]["disable_safety_checker"]),
            }
        }

        self.step_values = {
            "pro": {
                "guidance": 0.1,
                "steps": 1,
                "interval": 0.1,
                "safety_tolerance": 1,
            },
            "dev": {
                "guidance": 0.1,
                "num_outputs": 1,
                "output_quality": 1,
                "prompt_strength": 0.01,
                "num_inference_steps": 1,
            },
            "schnell": {
                "num_outputs": 1,
                "output_quality": 1,
            }
        }

    def update_parameter_fields(self, event=None):
        for widget in self.param_frame.winfo_children():
            widget.destroy()

        self.sliders = {}

        model = self.model_var.get()
        self.create_common_fields()
        self.create_model_specific_fields(model)

    def create_common_fields(self):
        row = 0
        for param, var in self.common_vars.items():
            if param == "randomize_seed":
                continue
            if param == "upscale":
                checkbutton = ttk.Checkbutton(self.param_frame, text="Upscale", variable=var)
                checkbutton.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky="w")
            else:
                ttk.Label(self.param_frame, text=f"{param.replace('_', ' ').title()}:").grid(row=row, column=0, padx=5,
                                                                                             pady=5, sticky="w")
                if param == "aspect_ratio":
                    ttk.Combobox(self.param_frame, textvariable=var,
                                 values=["16:9", "21:9", "1:1", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"],
                                 state="readonly").grid(row=row, column=1, padx=5, pady=5, sticky="we")
                elif param == "seed":
                    seed_frame = ttk.Frame(self.param_frame)
                    seed_frame.grid(row=row, column=1, padx=5, pady=5, sticky="we")

                    seed_entry = ttk.Entry(seed_frame, textvariable=var)
                    seed_entry.grid(row=0, column=0, sticky="we")
                    seed_frame.columnconfigure(0, weight=1)

                    randomize_check = ttk.Checkbutton(seed_frame, text="Randomize",
                                                      variable=self.common_vars["randomize_seed"])
                    randomize_check.grid(row=0, column=1, padx=(5, 0))
                else:
                    ttk.Entry(self.param_frame, textvariable=var).grid(row=row, column=1, padx=5, pady=5, sticky="we")
            row += 1

    def create_model_specific_fields(self, model: str) -> None:
        row = len(self.common_vars)
        for param, var in self.model_specific_vars[model].items():
            if param == "image_path":
                ttk.Label(self.param_frame, text="Image Path:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
                entry = ttk.Entry(self.param_frame, textvariable=var)
                entry.grid(row=row, column=1, padx=5, pady=5, sticky="we")
                ttk.Button(self.param_frame, text="Browse", command=self.browse_image).grid(row=row, column=2, padx=5,
                                                                                            pady=5)
            elif param == "disable_safety_checker":
                checkbutton = ttk.Checkbutton(self.param_frame, text="Disable Safety Checker", variable=var)
                checkbutton.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky="w")
            elif param == "output_format":
                ttk.Label(self.param_frame, text="Output Format:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
                format_combo = ttk.Combobox(self.param_frame, textvariable=var, values=["webp", "jpg", "png"],
                                            state="readonly")
                format_combo.grid(row=row, column=1, padx=5, pady=5, sticky="we")
                format_combo.set(self.default_values[model]["output_format"])
            else:
                ttk.Label(self.param_frame, text=f"{param.replace('_', ' ').title()}:").grid(row=row, column=0, padx=5,
                                                                                             pady=5, sticky="w")
                if param in ["guidance", "num_outputs", "output_quality", "prompt_strength", "num_inference_steps",
                             "steps", "interval", "safety_tolerance"]:
                    slider_frame = ttk.Frame(self.param_frame)
                    slider_frame.grid(row=row, column=1, padx=5, pady=5, sticky="we")

                    if model == "pro":
                        if param == "guidance":
                            min_val, max_val, step = 2, 5, 0.1
                        elif param == "steps":
                            min_val, max_val, step = 1, 50, 1
                        elif param == "interval":
                            min_val, max_val, step = 1, 4, 0.1
                        elif param == "safety_tolerance":
                            min_val, max_val, step = 1, 5, 1
                    elif model == "dev":
                        if param == "guidance":
                            min_val, max_val, step = 0, 10, 0.1
                        elif param == "num_outputs":
                            min_val, max_val, step = 1, 4, 1
                        elif param == "output_quality":
                            min_val, max_val, step = 0, 100, 1
                        elif param == "prompt_strength":
                            min_val, max_val, step = 0, 1, 0.01
                        elif param == "num_inference_steps":
                            min_val, max_val, step = 1, 50, 1
                    elif model == "schnell":
                        if param == "num_outputs":
                            min_val, max_val, step = 1, 4, 1
                        elif param == "output_quality":
                            min_val, max_val, step = 0, 100, 1

                    style = ttk.Style()
                    if platform.system() == "Darwin":
                        style.theme_use("aqua")
                    elif platform.system() == "Windows":
                        style.theme_use("xpnative")
                    else:
                        style.theme_use("clam")
                    style.configure("Value.TLabel", anchor="e", width=6)
                    style.configure("blue.Horizontal.TProgressbar", troughcolor='lightgray', background='blue')

                    format_string = ".2f" if step < 0.1 else (".1f" if step < 1 else "d")
                    value_label = ttk.Label(slider_frame, text=f"{var.get():{format_string}}", style="Value.TLabel")
                    value_label.grid(row=0, column=3, padx=(5, 0))

                    def update_value(value, label, var, param_name):
                        float_value = float(value)
                        model = self.model_var.get()
                        step_value = self.step_values[model].get(param_name, 1)
                        if step_value >= 1:
                            snapped_value = round(float_value)
                        else:
                            snapped_value = round(float_value / step_value) * step_value
                        format_string = ".2f" if step_value < 0.1 else (".1f" if step_value < 1 else "d")
                        var.set(snapped_value)
                        label.config(text=f"{snapped_value:{format_string}}")
                        return snapped_value

                    def create_update_function(label, var, param_name):
                        return lambda value: update_value(value, label, var, param_name)

                    slider = ttk.Scale(
                        slider_frame,
                        from_=min_val,
                        to=max_val,
                        orient=tk.HORIZONTAL,
                        command=create_update_function(value_label, var, param)
                    )
                    slider.grid(row=0, column=1, padx=5, sticky="we")
                    self.sliders[param] = slider
                    slider_frame.columnconfigure(1, weight=1)  # Make the slider expandable
                    slider.set(update_value(var.get(), value_label, var, param))  # Set initial value

                    def reset_slider(event, s=slider, label=value_label, value=var, m=model, p=param):
                        default_value = self.default_values[m].get(p, value.get())
                        s.set(update_value(default_value, label, value, p))

                    value_label.bind("<Button-1>", reset_slider)
                else:
                    entry = ttk.Entry(self.param_frame, textvariable=var)
                    entry.grid(row=row, column=1, padx=5, pady=5, sticky="we")
            row += 1

    def browse_image(self):
        if filename := tk.filedialog.askopenfilename(
                filetypes=[("Image files", "*.jpg *.jpeg *.png *.webm")]
        ):
            self.model_specific_vars["dev"]["image_path"].set(filename)

    def generate_image(self):
        if self.is_generating:
            return  # Prevent multiple generations

        model = self.model_var.get()
        prompt_text = self.prompt_text.get("1.0", tk.END).strip()

        if self.common_vars["randomize_seed"].get():
            self.common_vars["seed"].set(random.randint(0, 2 ** 32 - 1))

        properties = {
            "prompt": prompt_text,
            "seed": self.common_vars["seed"].get(),
            **{k: v.get() for k, v in self.common_vars.items() if k not in ["seed", "randomize_seed"]},
            **{k: v.get() for k, v in self.model_specific_vars[model].items() if k != "image_path"}
        }

        if model == "dev" and self.model_specific_vars["dev"]["image_path"].get():
            image_path = self.model_specific_vars["dev"]["image_path"].get()
            try:
                with open(image_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                properties["image"] = f"data:image/png;base64,{encoded_string}"
            except FileNotFoundError:
                self.output_text.config(state="normal")
                self.output_text.insert(tk.END, f"Image file not found at path: {image_path}\n")
                self.output_text.config(state="disabled")
                return

        self.output_text.config(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, f"Generating image with {model} model...\n")
        self.output_text.insert(tk.END, "Properties:\n")
        for key, value in properties.items():
            if key == "image":
                self.output_text.insert(tk.END, f"  {key}: [base64 encoded image]\n")
            else:
                self.output_text.insert(tk.END, f"  {key}: {value}\n")
        self.output_text.insert(tk.END, "\n")
        self.master.update_idletasks()

        # Start the image generation in a separate thread
        self.is_generating = True
        self.update_generate_button()
        thread = threading.Thread(target=self._generate_image_task, args=(model, properties))
        thread.start()

    def show_loading_screen(self):
        # Get the position and size of the output text box
        text_box = self.output_text
        x = text_box.winfo_rootx() - self.master.winfo_rootx()
        y = text_box.winfo_rooty() - self.master.winfo_rooty()
        width = text_box.winfo_width()
        height = text_box.winfo_height()

        # Create a Toplevel window that covers only the output text box
        loading_screen = tk.Toplevel(self.master)
        loading_screen.geometry(f"{width}x{height}+{x}+{y}")
        loading_screen.overrideredirect(True)  # Remove window decorations
        loading_screen.attributes("-alpha", 0.7)  # Set transparency
        loading_screen.attributes("-topmost", True)  # Ensure it's on top

        # Create a frame to hold the loading message
        frame = ttk.Frame(loading_screen, style="Overlay.TFrame")
        frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Add a label to display the loading message
        loading_label = ttk.Label(frame, text="Generating...", font=("Helvetica", 14), background="white")
        loading_label.pack(expand=True)

        loading_screen.update_idletasks()
        return loading_screen

    def _generate_image_task(self, model, properties):
        time_start = perf_counter()

        try:
            output, current_time, results_dir = generate_image(model, properties)

            self.master.after(0, lambda: process_generated_images(output, current_time, results_dir, properties, model,
                                                                  self.output_text))

            time_stop = perf_counter()
            self.master.after(0, lambda: self.output_text.insert(tk.END, f"Time: {time_stop - time_start:.2f}s\n"))
            self.master.after(0, lambda: self.output_text.insert(tk.END, "Image generation and upscaling complete!\n"))
            self.master.after(0, self.load_images_from_results)

        except Exception as e:
            self.master.after(0, lambda: self.output_text.insert(tk.END, f"Error: {str(e)}\n"))

        finally:
            self.master.after(0, lambda: self.output_text.config(state="disabled"))
            self.is_generating = False
            self.master.after(0, self.update_generate_button)

    def update_generate_button(self):
        if self.is_generating:
            self.generate_button.pack_forget()
            self.progress_bar.pack(fill=tk.X)
            self.progress_bar.start(10)  # Start the progress bar animation
        else:
            self.progress_bar.stop()  # Stop the progress bar animation
            self.progress_bar.pack_forget()
            self.generate_button.pack(fill=tk.X)
        self.master.update_idletasks()

    def setup_keyboard_shortcuts(self):
        self.master.bind("<Tab>", focus_next_widget)
        self.master.bind("<Shift-Tab>", focus_previous_widget)
        self.master.bind("<Control-Return>", lambda event: self.generate_image())
        self.master.bind("<Command-Return>", lambda event: self.generate_image())

        self.prompt_text.bind("<Tab>", focus_next_widget)
        self.prompt_text.bind("<Shift-Tab>", focus_previous_widget)

    def create_gallery(self):
        # Create a notebook widget
        self.gallery_notebook = ttk.Notebook(self.gallery_frame)
        self.gallery_notebook.pack(fill=tk.BOTH, expand=True)

        # Create a frame for the gallery inside the notebook
        self.gallery_tab = ttk.Frame(self.gallery_notebook)
        self.gallery_notebook.add(self.gallery_tab, text="Gallery")

        # Create a canvas for the gallery (this will make it scrollable)
        self.gallery_canvas = tk.Canvas(self.gallery_tab, width=330, relief=tk.SUNKEN)
        self.gallery_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Add a vertical scrollbar
        self.gallery_scrollbar = ttk.Scrollbar(self.gallery_tab, orient="vertical", command=self.gallery_canvas.yview)
        self.gallery_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.gallery_canvas.configure(yscrollcommand=self.gallery_scrollbar.set)

        # Create a frame inside the canvas to hold the images
        self.gallery_images_frame = ttk.Frame(self.gallery_canvas)
        self.gallery_canvas.create_window((0, 0), window=self.gallery_images_frame, anchor=tk.NW)

        # Configure the canvas to update its scroll region when the size of the frame changes
        self.gallery_images_frame.bind("<Configure>", self.on_frame_configure)

        # Bind mousewheel event to the canvas
        self.gallery_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.gallery_canvas.bind("<Enter>", self._bound_to_mousewheel)
        self.gallery_canvas.bind("<Leave>", self._unbound_to_mousewheel)

        # Load initial images
        self.load_images_from_results()

    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.gallery_canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.gallery_canvas.yview_scroll(1, "units")

    def _bind_mousewheel(self, widget):
        # Bind mousewheel event to the widget
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

    def _bound_to_mousewheel(self, event):
        self.gallery_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.gallery_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.gallery_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.gallery_canvas.unbind_all("<MouseWheel>")
        self.gallery_canvas.unbind_all("<Button-4>")
        self.gallery_canvas.unbind_all("<Button-5>")

    def on_frame_configure(self, event):
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def load_images_from_results(self):
        results_folder = "results"
        if not os.path.exists(results_folder):
            return

        # Clear existing images
        for widget in self.gallery_images_frame.winfo_children():
            widget.destroy()

        # Get list of image files, sorted by modification time (newest first)
        image_files = sorted(
            [f for f in os.listdir(results_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))],
            key=lambda x: os.path.getmtime(os.path.join(results_folder, x)),
            reverse=True
        )

        row, col = 0, 0
        for img_file in image_files:
            img_path = os.path.join(results_folder, img_file)
            self.add_image_to_gallery(img_path, row, col)
            col += 1
            if col == 3:  # Move to next row after 3 columns
                col = 0
                row += 1

        self.gallery_images_frame.update_idletasks()
        self.gallery_canvas.config(scrollregion=self.gallery_canvas.bbox("all"))

    def add_image_to_gallery(self, img_path, row, col):
        # Open the image and create a thumbnail
        with Image.open(img_path) as img:
            img.thumbnail((100, 100))  # Resize image to fit in the gallery
            photo = ImageTk.PhotoImage(img)

        # Create a label with the image and add it to the gallery
        label = ttk.Label(self.gallery_images_frame, image=photo)
        label.image = photo  # Keep a reference to prevent garbage collection
        label.grid(row=row, column=col, padx=5, pady=5)

        # Bind click event to open full-size image
        label.bind("<Button-1>", lambda e, path=img_path: self.open_full_size_image(path))

        # Bind mousewheel event to the label
        self._bind_mousewheel(label)

    def open_full_size_image(self, img_path):
        # Open the full-size image in a new window
        top = tk.Toplevel(self.master)
        top.title("Full Size Image")

        # Create a main frame to hold everything
        main_frame = ttk.Frame(top)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create a canvas to hold the image
        canvas = tk.Canvas(main_frame)
        canvas.pack(fill=tk.BOTH, expand=True)

        # Open the image and store it in memory
        with Image.open(img_path) as img:
            self.full_size_image = img.copy()

        # Create a frame to hold the text widget and buttons
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, expand=False, side=tk.BOTTOM)

        # Variables for delayed resizing
        resize_timer = None
        last_resize_time = 0
        resize_delay = 200  # milliseconds

        # Function to resize the image
        def resize_image():
            nonlocal last_resize_time
            current_time = time.time() * 1000  # Convert to milliseconds
            if current_time - last_resize_time < resize_delay:
                return

            # Get the current window size
            window_width = top.winfo_width()
            window_height = top.winfo_height()
            control_height = control_frame.winfo_height()

            # Check if the window size is valid
            if window_width <= 1 or window_height <= 1:
                return  # Skip resizing if the window is too small

            # Calculate the scaling factor
            img_width, img_height = self.full_size_image.size
            available_height = window_height - control_height
            scale = min(window_width / img_width, available_height / img_height)

            # Resize the image
            new_width = max(1, int(img_width * scale))
            new_height = max(1, int(img_height * scale))
            resized_img = self.full_size_image.copy().resize((new_width, new_height), Image.LANCZOS)

            # Create a PhotoImage object
            photo = ImageTk.PhotoImage(resized_img)

            # Update the canvas
            canvas.delete("all")
            canvas.create_image(window_width // 2, available_height // 2, anchor=tk.CENTER, image=photo)
            canvas.image = photo  # Keep a reference

            last_resize_time = current_time

        # Function to schedule delayed resize
        def schedule_resize(event=None):
            nonlocal resize_timer
            if resize_timer is not None:
                top.after_cancel(resize_timer)
            resize_timer = top.after(resize_delay, resize_image)

        # Read metadata from EXIF
        metadata = read_image_metadata(img_path)
        if metadata:
            # Create a text widget to display metadata
            text_widget = tk.Text(control_frame, height=10, wrap=tk.WORD)
            text_widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
            text_widget.insert(tk.END, json.dumps(metadata, indent=2))
            text_widget.config(state=tk.DISABLED)  # Make it read-only

            # Create a frame for buttons
            button_frame = ttk.Frame(control_frame)
            button_frame.pack(side=tk.RIGHT, fill=tk.Y)

            # Create a button to set widgets according to EXIF data
            set_widgets_button = ttk.Button(button_frame, text="🔧 Set Widgets",
                                            command=lambda: self.set_widgets_and_close(metadata, top))
            set_widgets_button.pack(side=tk.TOP, padx=5, pady=5)

            # Create an Upscale button
            upscale_button = ttk.Button(button_frame, text="🔍 Upscale",
                                        command=lambda: self.upscale_image(img_path, metadata, top))
            upscale_button.pack(side=tk.TOP, padx=5, pady=5)

            # Create a button to copy the image to clipboard
            copy_button = ttk.Button(button_frame, text="📋 Clipboard",
                                     command=lambda: copy_image_to_clipboard(img_path))
            copy_button.pack(side=tk.TOP, padx=2, pady=2)

            # Create a button to open image location
            open_location_button = ttk.Button(button_frame, text="📂 Open", style="Blue.TButton",
                                              command=lambda: open_file_location(img_path))
            open_location_button.pack(side=tk.TOP, padx=5, pady=5)

            # Create a Delete button
            style = ttk.Style()
            style.configure("Red.TButton", foreground="#FF7C8B")
            style.configure("Blue.TButton", foreground="lightblue")

            delete_button = ttk.Button(button_frame, text="🗑️ Delete", style="Red.TButton",
                                       command=lambda: self.delete_image(img_path, top))
            delete_button.pack(side=tk.TOP, padx=5, pady=5)

        # Bind the resize event
        top.bind("<Configure>", schedule_resize)
        top.bind("<ButtonRelease-1>", schedule_resize)  # Trigger resize on mouse button release

        # Bind click event to close the window
        canvas.bind("<Button-1>", lambda e: top.destroy())

        # Initial resize
        top.update_idletasks()  # Ensure the window size is updated
        top.after(100, resize_image)  # Schedule the initial resize after a short delay

    def upscale_image(self, img_path, metadata, window):
        if upscaled_data := upscale_image(img_path):
            # Generate a new filename for the upscaled image
            base_name, ext = os.path.splitext(img_path)
            upscaled_path = f"{base_name}_upscaled{ext}"

            # Save the upscaled image
            with open(upscaled_path, "wb") as upscaled_file:
                upscaled_file.write(upscaled_data)

            # Update metadata
            metadata["upscaled"] = True

            # Convert metadata to a JSON string
            metadata_json = json.dumps(metadata)

            # Create or update EXIF data
            try:
                img = Image.open(upscaled_path)
                exif_dict = piexif.load(img.info.get("exif", b""))
            except (KeyError, ValueError, FileNotFoundError):
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

            # Add metadata to EXIF
            user_comment = piexif.helper.UserComment.dump(metadata_json)
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment

            # Convert EXIF dict to bytes
            exif_bytes = piexif.dump(exif_dict)

            # Save the image with updated EXIF data
            img.save(upscaled_path, "JPEG", exif=exif_bytes, quality=95)

            # Close the current window and open the new upscaled image
            window.destroy()
            self.open_full_size_image(upscaled_path)

            # Refresh the gallery
            self.load_images_from_results()

            # Show a success message
            tk.messagebox.showinfo("Upscale Complete", f"Image upscaled and saved as {os.path.basename(upscaled_path)}")
        else:
            # Show an error message if upscaling failed
            tk.messagebox.showerror("Upscale Failed", "Failed to upscale the image.")

    def delete_image(self, img_path, window):
        # Ask for confirmation
        if tk.messagebox.askyesno("Delete Image", "Are you sure you want to delete this image?"):
            try:
                os.remove(img_path)
                window.destroy()
                self.load_images_from_results()  # Refresh the gallery
            except Exception as e:
                tk.messagebox.showerror("Error", f"Failed to delete image: {str(e)}")

    def set_widgets_and_close(self, metadata, window):
        self.set_widgets_from_metadata(metadata)
        window.destroy()

    def set_widgets_from_metadata(self, metadata):
        # Set model
        if "model" in metadata:
            self.model_var.set(metadata["model"])
            self.update_parameter_fields()

        # Set prompt
        if "prompt" in metadata:
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert(tk.END, metadata["prompt"])

        # Set common variables
        for key, var in self.common_vars.items():
            if key in metadata:
                var.set(metadata[key])

        # Set model-specific variables
        model = metadata.get("model", self.model_var.get())
        for key, var in self.model_specific_vars[model].items():
            if key in metadata:
                var.set(metadata[key])
                if key in self.sliders:
                    self.sliders[key].set(metadata[key])

        # Always set randomize seed to False when setting widgets from metadata
        self.common_vars["randomize_seed"].set(False)

        # Force update of all sliders
        for param, slider in self.sliders.items():
            value = self.model_specific_vars[model][param].get()
            slider.set(value)

        # Update the UI
        self.master.update_idletasks()


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


def check_updates():
    if current_version := get_current_version():
        is_latest, message = check_latest_version(current_version)
        print(message)
        if not is_latest:
            update = input("Update to the latest version from GitHub? (Y/n): ")
            if update.lower() in ["y", "yes", ""]:
                update_application()
                restart_application()
    else:
        print("Unable to determine the current version.")


def main():
    check_updates()
    initialize_app()
    root = tk.Tk()
    gui = ImageGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()