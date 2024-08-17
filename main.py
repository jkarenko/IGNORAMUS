import base64
import datetime
import os
import random
import tkinter as tk
from time import perf_counter
from tkinter import ttk, filedialog

import replicate
import requests
from PIL import Image, ImageTk


def focus_previous_widget(event):
    event.widget.tk_focusPrev().focus()
    return "break"


def focus_next_widget(event):
    event.widget.tk_focusNext().focus()
    return "break"


class ImageGeneratorGUI:
    def __init__(self, master):
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
        self.master = master
        master.title("Image Generator GUI")
        master.geometry("600x700")

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
        # Model selection
        ttk.Label(self.master, text="Select Model:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.model_var = tk.StringVar(value="pro")
        self.model_combo = ttk.Combobox(self.master, textvariable=self.model_var, values=["pro", "dev", "schnell"],
                                        state="readonly")
        self.model_combo.grid(row=0, column=1, padx=10, pady=10, sticky="we")
        self.model_combo.bind("<<ComboboxSelected>>", self.update_parameter_fields)

        # Common parameters
        ttk.Label(self.master, text="Prompt:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.prompt_text = tk.Text(self.master, height=4, width=50)
        self.prompt_text.grid(row=1, column=1, padx=10, pady=10, sticky="we")

        # Model-specific parameters
        self.param_frame = ttk.Frame(self.master)
        self.param_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="we")

        # Generate button
        self.generate_button = ttk.Button(self.master, text="Generate Image", command=self.generate_image)
        self.generate_button.grid(row=3, column=0, columnspan=2, padx=10, pady=10)

        # Output
        self.output_text = tk.Text(self.master, height=10, width=70, state="disabled")
        self.output_text.grid(row=4, column=0, columnspan=2, padx=10, pady=10)

        self.initialize_variables()
        self.update_parameter_fields()

        self.gallery_frame = ttk.Frame(self.master)
        self.gallery_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="we")

    def initialize_variables(self):
        self.common_vars = {
            "aspect_ratio": tk.StringVar(value="16:9"),
            "seed": tk.IntVar(value=random.randint(0, 2 ** 32 - 1)),
            "randomize_seed": tk.BooleanVar(value=True)
        }

        self.model_specific_vars = {
            "pro": {
                "steps": tk.IntVar(value=25),
                "guidance": tk.DoubleVar(value=3.0),
                "interval": tk.DoubleVar(value=2.0),
                "safety_tolerance": tk.IntVar(value=2),
            },
            "dev": {
                "image_path": tk.StringVar(),
                "guidance": tk.DoubleVar(value=3.5),
                "num_outputs": tk.IntVar(value=1),
                "output_format": tk.StringVar(value="jpg"),
                "output_quality": tk.IntVar(value=80),
                "prompt_strength": tk.DoubleVar(value=0.8),
                "num_inference_steps": tk.IntVar(value=50),
                "disable_safety_checker": tk.BooleanVar(value=True),
            },
            "schnell": {
                "num_outputs": tk.IntVar(value=1),
                "output_format": tk.StringVar(value="jpg"),
                "output_quality": tk.IntVar(value=80),
                "disable_safety_checker": tk.BooleanVar(value=True),
            }
        }

        self.default_values = {
            "pro": {
                "steps": 25,
                "guidance": 3.0,
                "interval": 2.0,
                "safety_tolerance": 2,
            },
            "dev": {
                "guidance": 3.5,
                "num_outputs": 1,
                "output_quality": 80,
                "prompt_strength": 0.8,
                "num_inference_steps": 50,
                "output_format": "jpg",
            },
            "schnell": {
                "num_outputs": 1,
                "output_quality": 80,
                "output_format": "jpg",
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

        model = self.model_var.get()
        self.create_common_fields()
        self.create_model_specific_fields(model)

    def create_common_fields(self):
        row = 0
        for param, var in self.common_vars.items():
            if param == "randomize_seed":
                continue
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
                    style.configure("Value.TLabel", anchor="e", width=6)

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
                    slider_frame.columnconfigure(1, weight=1)  # Make the slider expandable
                    slider.set(update_value(var.get(), value_label, var, param))  # Set initial value

                    def reset_slider(event, s=slider, l=value_label, v=var, m=model, p=param):
                        default_value = self.default_values[m].get(p, v.get())
                        s.set(update_value(default_value, l, v, p))

                    value_label.bind("<Button-1>", reset_slider)
                else:
                    entry = ttk.Entry(self.param_frame, textvariable=var)
                    entry.grid(row=row, column=1, padx=5, pady=5, sticky="we")
            row += 1

    def browse_image(self):
        filename = tk.filedialog.askopenfilename(
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webm")]
        )
        if filename:
            self.model_specific_vars["dev"]["image_path"].set(filename)

    def generate_image(self):
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

        # Schedule the long-running task
        self.master.after(100, self._generate_image_task, model, properties)
        self.load_images_from_results()

    def _generate_image_task(self, model, properties):
        time_start = perf_counter()

        # self.output_text.insert(tk.END, "Sending to API:\n")
        # self.output_text.insert(tk.END, f"{properties}\n\n")
        # self.master.update_idletasks()

        try:
            output = replicate.run(f"black-forest-labs/flux-{model}", input=properties)

            # self.output_text.insert(tk.END, "Raw API output:\n")
            # self.output_text.insert(tk.END, f"{output}\n\n")
        except Exception as e:
            self.output_text.insert(tk.END, f"Error: {str(e)}\n")
            self.output_text.config(state="disabled")
            return
        time_stop = perf_counter()

        self.output_text.insert(tk.END, f"Time: {time_stop - time_start:.2f}s\n")

        if not os.path.exists("results"):
            os.makedirs("results")

        if isinstance(output, str):
            output = [output]

        current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        for idx, url in enumerate(output):
            response = requests.get(url)
            file_name = f"results/img_{current_time}{f'_{str(idx)}' if len(output) > 1 else ''}.jpg"
            with open(file_name, "wb") as file:
                file.write(response.content)
            self.output_text.insert(tk.END, f"Saved image: {file_name}\n")

        self.output_text.insert(tk.END, "Image generation complete!\n")
        self.output_text.config(state="disabled")

    def setup_keyboard_shortcuts(self):
        self.master.bind("<Tab>", focus_next_widget)
        self.master.bind("<Shift-Tab>", focus_previous_widget)
        self.master.bind("<Control-Return>", lambda event: self.generate_image())
        self.master.bind("<Command-Return>", lambda event: self.generate_image())

        self.prompt_text.bind("<Tab>", focus_next_widget)
        self.prompt_text.bind("<Shift-Tab>", focus_previous_widget)

    def create_gallery(self):
        # Create a canvas for the gallery
        self.gallery_canvas = tk.Canvas(self.gallery_frame, height=100)
        self.gallery_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Add a horizontal scrollbar
        self.gallery_scrollbar = ttk.Scrollbar(self.gallery_frame, orient=tk.HORIZONTAL,
                                               command=self.gallery_canvas.xview)
        self.gallery_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.gallery_canvas.configure(xscrollcommand=self.gallery_scrollbar.set)

        # Create a frame inside the canvas to hold the images
        self.gallery_images_frame = ttk.Frame(self.gallery_canvas)
        self.gallery_canvas.create_window((0, 0), window=self.gallery_images_frame, anchor=tk.NW)

        # Bind the configure event to update the scroll region
        self.gallery_images_frame.bind("<Configure>", self.on_frame_configure)

        # Load initial images
        self.load_images_from_results()

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

        for img_file in image_files:
            img_path = os.path.join(results_folder, img_file)
            self.add_image_to_gallery(img_path)

    def on_frame_configure(self, event):
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def add_image_to_gallery(self, img_path):
        # Open the image and create a thumbnail
        with Image.open(img_path) as img:
            img.thumbnail((100, 100))  # Resize image to fit in the gallery
            photo = ImageTk.PhotoImage(img)

        # Create a label with the image and add it to the gallery
        label = ttk.Label(self.gallery_images_frame, image=photo)
        label.image = photo  # Keep a reference to prevent garbage collection
        label.pack(side=tk.LEFT, padx=5)

        # Bind click event to open full-size image
        label.bind("<Button-1>", lambda e, path=img_path: self.open_full_size_image(path))

    def open_full_size_image(self, img_path):
        # Open the full-size image in a new window
        top = tk.Toplevel(self.master)
        top.title("Full Size Image")

        with Image.open(img_path) as img:
            photo = ImageTk.PhotoImage(img)

        label = ttk.Label(top, image=photo)
        label.image = photo  # Keep a reference
        label.pack()


if __name__ == "__main__":
    root = tk.Tk()
    gui = ImageGeneratorGUI(root)
    root.mainloop()
