import datetime
import random
import threading
import time
from tkinter import ttk, filedialog

import piexif.helper
import requests
from PIL import ImageTk

from ignoramus.upscaler import upscale_image
from ignoramus.utils import *
from ignoramus.version_checker import check_updates
from ignoramus.image_generator import generate_image, process_generated_images, get_output_directory
from ignoramus.face_swapper import add_face_swap_button
from ignoramus.face_swapper import face_swap


class ImageGeneratorGUI:
    def __init__(self, master):
        self.face_image_path = tk.StringVar()
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

    def generate_image_keyboard(self):
        # Workaround: Erase the newline character added by the Enter key
        self.prompt_text.event_generate("<BackSpace>")
        self.generate_image()

    def generate_image(self):
        if self.is_generating:
            return

        self.is_generating = True
        self.update_generate_button()

        model = self.model_var.get()
        properties = self.get_properties()

        self.output_text.config(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, "Generating image...\n")

        threading.Thread(target=self._generate_image_task, args=(model, properties)).start()

    def get_properties(self):
        properties = {
            "prompt": self.prompt_text.get("1.0", tk.END).strip(),
        }

        # Add common properties
        for key, var in self.common_vars.items():
            if key == "randomize_seed" and var.get():
                properties["seed"] = random.randint(0, 2 ** 32 - 1)
            else:
                properties[key] = var.get()

        # Add model-specific properties
        model = self.model_var.get()
        for key, var in self.model_specific_vars[model].items():
            properties[key] = var.get()

        return properties

    def create_widgets(self):
        # Create a main frame to hold everything
        main_frame = ttk.Frame(self.master)
        main_frame.pack(side=tk.TOP, expand=False)

        # Create left frame for controls
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, expand=False)

        # Model selection
        ttk.Label(left_frame, text="Select Model:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.model_var = tk.StringVar(value="schnell")
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
        current_face_image_path = self.face_image_path.get()
        for widget in self.param_frame.winfo_children():
            widget.destroy()

        self.sliders = {}

        model = self.model_var.get()
        self.create_common_fields()
        self.create_model_specific_fields(model)
        self.face_image_path.set(current_face_image_path)

    def browse_face_image(self):
        if filename := filedialog.askopenfilename(
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp *.webm")]
        ):
            self.face_image_path.set(filename)

    def create_common_fields(self):
        row = 0
        for param, var in self.common_vars.items():
            if param == "randomize_seed":
                continue
            if param == "upscale":
                checkbutton = ttk.Checkbutton(self.param_frame, text="Upscale", variable=var)
                checkbutton.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky="w")
                ttk.Label(self.param_frame, text="Use Face From:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
                face_frame = ttk.Frame(self.param_frame)
                face_frame.grid(row=row, column=1, padx=5, pady=5, sticky="we")
                face_entry = ttk.Entry(face_frame, textvariable=self.face_image_path)  # Use self.face_image_path
                face_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
                browse_button = ttk.Button(face_frame, text="Browse", command=self.browse_face_image)
                browse_button.pack(side=tk.RIGHT)
                row += 1
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
                filetypes=[("Image files", "*.jpg *.jpeg *.png *.webm *.webp")]
        ):
            self.model_specific_vars["dev"]["image_path"].set(filename)

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
        try:
            output, current_time, results_dir = generate_image(model, properties)
            processed_images = process_generated_images(output, current_time, results_dir, properties, model)

            # Perform face swap if a face image is specified
            face_image_path = self.face_image_path.get()
            if face_image_path:
                for image in processed_images:
                    swapped_output = face_swap(face_image_path, image['file_name'])
                    if swapped_output:
                        # Download and save the face-swapped image
                        response = requests.get(swapped_output)
                        if response.status_code == 200:
                            # Save the face-swapped image temporarily
                            temp_file = f"{image['file_name']}_temp.jpg"
                            with open(temp_file, 'wb') as f:
                                f.write(response.content)

                            # Create EXIF metadata with original properties
                            exif_dict = create_exif_metadata(properties, model)

                            # Add face_swapped flag to the metadata
                            metadata = json.loads(
                                piexif.helper.UserComment.load(exif_dict["Exif"][piexif.ExifIFD.UserComment]))
                            metadata["face_swapped"] = True
                            exif_dict["Exif"][piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(
                                json.dumps(metadata))

                            exif_bytes = piexif.dump(exif_dict)

                            # Open the temporary image, add EXIF, and save it to the original filename
                            with Image.open(temp_file) as img:
                                img.save(image['file_name'], exif=exif_bytes, quality=95)

                            # Remove the temporary file
                            os.remove(temp_file)

                            image['face_swapped'] = True
                        else:
                            image['face_swapped'] = False
                    else:
                        image['face_swapped'] = False

            self.master.after(0, lambda: self.update_output_text(processed_images))
            self.master.after(0, self.load_images_from_results)

        except Exception as e:
            error_message = f"Error: {str(e)}\n"
            self.master.after(0, lambda: self.output_text.insert(tk.END, error_message))

        finally:
            self.is_generating = False
            self.master.after(0, self.update_generate_button)
    def update_output_text(self, processed_images):
        for image in processed_images:
            self.output_text.insert(tk.END, f"Saved image: {image['file_name']}\n")
            if image.get('face_swapped'):
                self.output_text.insert(tk.END, "Face swap applied successfully.\n")
            elif 'face_swapped' in image:
                self.output_text.insert(tk.END, "Face swap failed.\n")
            if image.get('upscaled'):
                self.output_text.insert(tk.END, "Image upscaled successfully.\n")
            else:
                self.output_text.insert(tk.END, "Done.\n")

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
        self.master.bind("<Control-Return>", lambda event: self.generate_image_keyboard())
        self.master.bind("<Command-Return>", lambda event: self.generate_image_keyboard())

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

        # Convert all WebP images to JPG
        for filename in os.listdir(results_folder):
            if filename.lower().endswith('.webp'):
                webp_path = os.path.join(results_folder, filename)
                jpg_path = os.path.join(results_folder, os.path.splitext(filename)[0] + '.jpg')
                try:
                    with Image.open(webp_path) as img:
                        img = img.convert('RGB')
                        img.save(jpg_path, 'JPEG', quality=95)
                    os.remove(webp_path)
                    print(f"Converted {filename} to JPG")
                except Exception as e:
                    print(f"Error converting {filename}: {str(e)}")

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
        try:
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
        except Exception as e:
            print(f"Error adding image to gallery: {img_path}")
            print(f"Error details: {str(e)}")

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

            # Create a Face Swap button
            add_face_swap_button(button_frame, img_path, "results", self.load_images_from_results)

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
            current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            results_dir = get_output_directory()
            new_filename = f"img_{current_time}.jpg"
            upscaled_path = os.path.join(results_dir, new_filename)

            # Save the upscaled image
            with open(upscaled_path, "wb") as upscaled_file:
                upscaled_file.write(upscaled_data)

            # Update metadata
            metadata["upscaled"] = True

            # Convert metadata to a JSON string
            metadata_json = json.dumps(metadata)

            # Create or update EXIF data
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

            # Add metadata to EXIF
            user_comment = piexif.helper.UserComment.dump(metadata_json)
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment

            # Convert EXIF dict to bytes
            exif_bytes = piexif.dump(exif_dict)

            # Save the image with updated EXIF data
            img = Image.open(upscaled_path)
            img.save(upscaled_path, "JPEG", exif=exif_bytes, quality=95)

            # Close the current window and open the new upscaled image
            window.destroy()
            self.open_full_size_image(upscaled_path)

            # Refresh the gallery
            self.load_images_from_results()

            # Show a success message
            tk.messagebox.showinfo("Upscale Complete", f"Image upscaled and saved as {new_filename}")
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


def main():
    check_updates()
    initialize_app()
    root = tk.Tk()
    gui = ImageGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
