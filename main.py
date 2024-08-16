import base64
import os
from time import perf_counter

import replicate
import requests

prompt_text = "Tall man with medium-short dark hair and a dark full beard is wearing a black shirt with long sleeves and sunglasses. He is playing an electric guitar on stage and singing. Dark, gritty, moody, professional photography, stoner rock."
model = "pro"
image_path = "/Users/jk/code/image-generator/a.png"
encoded_string = None

if model == "dev" and image_path:
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Image file not found at path: {image_path}")

properties_pro = {
    "steps": 25,
    "prompt": prompt_text,
    "guidance": 3,
    "interval": 2,
    "aspect_ratio": "16:9",
    "safety_tolerance": 5,
}

properties_dev = {
    "image": f"data:image/png;base64,{encoded_string}",
    "prompt": prompt_text,
    "guidance": 3,
    "num_outputs": 4,
    "aspect_ratio": "16:9",
    "output_format": "jpg",
    "output_quality": 90,
    "prompt_strength": .3,
    "num_inference_steps": 25,
    "disable_safety_checker": True,
}

properties_schnell = {
    "prompt": prompt_text,
    "num_outputs": 4,
    "aspect_ratio": "16:9",
    "output_format": "jpg",
    "output_quality": 90,
    "disable_safety_checker": True,
}

match model:
    case "pro":
        properties = properties_pro
    case "dev":
        properties = properties_dev
    case "schnell":
        properties = properties_schnell
    case _:
        raise ValueError("Invalid model. Must be one of 'pro', 'dev', 'schnell'")

time_start = perf_counter()
output = replicate.run("black-forest-labs/flux-pro", input=properties)
time_stop = perf_counter()

print(f"Time: {time_stop - time_start:.2f}s")

if not os.path.exists("results"):
    os.makedirs("results")

if isinstance(output, list):
    for idx, url in enumerate(output):
        response = requests.get(url)
        with open(f"results/output_image_{idx}.jpg", "wb") as file:
            file.write(response.content)
else:
    response = requests.get(output)
    with open("results/output_image.jpg", "wb") as file:
        file.write(response.content)
