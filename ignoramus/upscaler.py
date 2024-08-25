import base64

import replicate
import requests


def upscale_image(image_path):
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

        input_data = {
            "image": f"data:image/png;base64,{encoded_string}",
            "upscale": 2,
            "face_upsample": False,
            "background_enhance": False,
            "codeformer_fidelity": 0.98
        }

        if not (
            output := replicate.run(
                "sczhou/codeformer:7de2ea26c616d5bf2245ad0d5e24f0ff9a6204578a5c876db53142edd9d2cd56",
                input=input_data,
            )
        ):
            return None

        response = requests.get(output)
        return response.content if response.status_code == 200 else None
    except Exception as e:
        print(f"Error during upscaling: {str(e)}")
        return None
