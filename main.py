import base64
import os
import tkinter as tk
from time import perf_counter
from tkinter import ttk, filedialog

import replicate
import requests


class ImageGeneratorGUI:
    def __init__(self, master):
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

    def create_widgets(self):
        # Model selection
        ttk.Label(self.master, text="Select Model:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.model_var = tk.StringVar(value="pro")
        self.model_combo = ttk.Combobox(self.master, textvariable=self.model_var, values=["pro", "dev", "schnell"])
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
        self.output_text = tk.Text(self.master, height=10, width=70)
        self.output_text.grid(row=4, column=0, columnspan=2, padx=10, pady=10)

        self.initialize_variables()
        self.update_parameter_fields()

    def initialize_variables(self):
        # Common variables
        self.common_vars = {
            "aspect_ratio": tk.StringVar(value="16:9"),
        }

        # Model-specific variables
        self.model_specific_vars = {
            "pro": {
                "steps": tk.IntVar(value=25),
                "guidance": tk.DoubleVar(value=3.0),
                "interval": tk.IntVar(value=2),
                "safety_tolerance": tk.IntVar(value=5),
            },
            "dev": {
                "image_path": tk.StringVar(),
                "guidance": tk.DoubleVar(value=3.0),
                "num_outputs": tk.IntVar(value=4),
                "output_format": tk.StringVar(value="jpg"),
                "output_quality": tk.IntVar(value=90),
                "prompt_strength": tk.DoubleVar(value=0.3),
                "num_inference_steps": tk.IntVar(value=25),
                "disable_safety_checker": tk.BooleanVar(value=True),
            },
            "schnell": {
                "num_outputs": tk.IntVar(value=4),
                "output_format": tk.StringVar(value="jpg"),
                "output_quality": tk.IntVar(value=90),
                "disable_safety_checker": tk.BooleanVar(value=True),
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
            ttk.Label(self.param_frame, text=f"{param.replace('_', ' ').title()}:").grid(row=row, column=0, padx=5,
                                                                                         pady=5, sticky="w")
            ttk.Entry(self.param_frame, textvariable=var).grid(row=row, column=1, padx=5, pady=5, sticky="we")
            row += 1

    def create_model_specific_fields(self, model):
        row = len(self.common_vars)
        for param, var in self.model_specific_vars[model].items():
            if param == "image_path":
                ttk.Label(self.param_frame, text="Image Path:").grid(row=row, column=0, padx=5, pady=5, sticky="w")
                ttk.Entry(self.param_frame, textvariable=var).grid(row=row, column=1, padx=5, pady=5, sticky="we")
                ttk.Button(self.param_frame, text="Browse", command=self.browse_image).grid(row=row, column=2, padx=5,
                                                                                            pady=5)
            elif param == "disable_safety_checker":
                ttk.Checkbutton(self.param_frame, text="Disable Safety Checker", variable=var).grid(row=row, column=0,
                                                                                                    columnspan=2,
                                                                                                    padx=5, pady=5,
                                                                                                    sticky="w")
            else:
                ttk.Label(self.param_frame, text=f"{param.replace('_', ' ').title()}:").grid(row=row, column=0, padx=5,
                                                                                             pady=5, sticky="w")
                ttk.Entry(self.param_frame, textvariable=var).grid(row=row, column=1, padx=5, pady=5, sticky="we")
            row += 1

    def browse_image(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png;*.jpg;*.jpeg")])
        self.model_specific_vars["dev"]["image_path"].set(filename)

    def generate_image(self):
        model = self.model_var.get()
        prompt_text = self.prompt_text.get("1.0", tk.END).strip()

        properties = {
            "prompt": prompt_text,
            **{k: v.get() for k, v in self.common_vars.items()},
            **{k: v.get() for k, v in self.model_specific_vars[model].items() if k != "image_path"}
        }

        if model == "dev" and self.model_specific_vars["dev"]["image_path"].get():
            image_path = self.model_specific_vars["dev"]["image_path"].get()
            try:
                with open(image_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                properties["image"] = f"data:image/png;base64,{encoded_string}"
            except FileNotFoundError:
                self.output_text.insert(tk.END, f"Image file not found at path: {image_path}\n")
                return

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, f"Generating image with {model} model...\n")
        self.master.update_idletasks()

        time_start = perf_counter()
        try:
            output = replicate.run(f"black-forest-labs/flux-{model}", input=properties)
        except Exception as e:
            self.output_text.insert(tk.END, f"Error: {str(e)}\n")
            return
        time_stop = perf_counter()

        self.output_text.insert(tk.END, f"Time: {time_stop - time_start:.2f}s\n")

        if not os.path.exists("results"):
            os.makedirs("results")

        if isinstance(output, str):
            output = [output]

        for idx, url in enumerate(output):
            response = requests.get(url)
            file_name = f"results/img_{time_start}{"_" + idx if len(output) > 1 else ""}.jpg"
            with open(file_name, "wb") as file:
                file.write(response.content)
            self.output_text.insert(tk.END, f"Saved image: {file_name}\n")

        self.output_text.insert(tk.END, "Image generation complete!\n")


if __name__ == "__main__":
    root = tk.Tk()
    gui = ImageGeneratorGUI(root)
    root.mainloop()
