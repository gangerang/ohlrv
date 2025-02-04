#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash
import requests, json, subprocess
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.secret_key = "CHANGE_ME_IN_PRODUCTION"  # Replace with a secure key

# Updated path for dezoomify in the container.
PATH_DEZOOMIFY = '/usr/local/bin/dezoomify-rs'

# Mapping dictionary (same as your script)
ms_mapping = {
    'Ay': {'number': 3005, 'name': 'Abury'},
    'Ae': {'number': 3010, 'name': 'Armidale'},
    'Be': {'number': 3015, 'name': 'Bourke'},
    'Cma': {'number': 3020, 'name': 'Cooma'},
    'Cta': {'number': 3025, 'name': 'Cootamundra'},
    'Do': {'number': 3030, 'name': 'Dubbo'},
    'Fs': {'number': 3035, 'name': 'Forbes'},
    'Gbn': {'number': 3040, 'name': 'Goulburn'},
    'Gfn': {'number': 3050, 'name': 'Grafton'},
    'Hy': {'number': 3060, 'name': 'Hay'},
    'Ky': {'number': 3065, 'name': 'Kempsey'},
    'Md': {'number': 3070, 'name': 'Maitland'},
    'Me': {'number': 3080, 'name': 'Moree'},
    'Na': {'number': 3085, 'name': 'Nowra'},
    'Oe': {'number': 3090, 'name': 'Orange'},
    'Sy': {'number': 3000, 'name': 'Sydney'},
    'Th': {'number': 3100, 'name': 'Tamworth'},
    'Te': {'number': 3105, 'name': 'Taree'},
    'Wga': {'number': 3110, 'name': 'Wagga Wagga'},
    'Wa': {'number': 3115, 'name': 'Wilcannia'}
}

def get_small_number(ms):
    return ms_mapping.get(ms, {}).get('number')

def print_ms_to_small_numbers():
    return "\n".join(f"{ms}: {info['number']} ({info['name']})" for ms, info in ms_mapping.items())

# URL constants for image fetching
URL_SLASH = '%2F'
DOWNLOAD_FORMAT = '.jpg'
URL_START = 'https://api.lrsnative.com.au/hlrv/iiif/2/'
URL_END_INFO = 'info.json'
URL_END_JPG = f'full/full/0/default{DOWNLOAD_FORMAT}'
URL_END_PREVIEW = f'full/1024,/0/default{DOWNLOAD_FORMAT}'

def fetch_url(mid_number, file_end, mid_eir, mid_source, file_source, file_big, file_small):
    if mid_number <= 100:
        mid_range = '1-100'
    elif mid_number <= 200:
        mid_range = '101-200'
    elif mid_number <= 300:
        mid_range = '201-300'
    elif mid_number <= 400:
        mid_range = '301-400'
    else:
        mid_range = '401-500'
    url_info = f'{URL_START}{mid_eir}{URL_SLASH}{mid_source}{URL_SLASH}{mid_range}{URL_SLASH}{mid_number}{URL_SLASH}{file_source}_{file_big}_{file_small}{file_end}.jp2/{URL_END_INFO}'
    r = requests.get(url_info, verify=True)
    return mid_number, r.status_code, url_info, r.text

def download_image(url_info, mid_file, preview):
    if preview:
        url_preview = url_info.replace(URL_END_INFO, URL_END_PREVIEW)
        # In a web context, you might send this URL to your template rather than opening a browser.
        print('Preview image URL:', url_preview)
    
    # Call dezoomify using the updated executable path
    result = subprocess.run([PATH_DEZOOMIFY, '-l', url_info, f'{mid_file}{DOWNLOAD_FORMAT}'])
    if result.returncode != 0:
        return f'Error during dezoomify execution: {result.stderr}'
    else:
        return f'Image successfully saved to {mid_file}{DOWNLOAD_FORMAT}'

def search_and_download(file_source, file_big, file_small, file_sheet, file_part, mid_number_start, mid_number_end, preview):
    file_end = f'P{file_sheet}J{file_part}' if file_sheet else f'J{file_part}'
    
    if not any(char.isdigit() for char in file_small):
        ms_lookup = get_small_number(file_small)
        if ms_lookup is None:
            return False, f"Invalid file_small parameter. Valid options:\n{print_ms_to_small_numbers()}"
        else:
            file_small = str(ms_lookup)
    
    mid_eir = 'eirCP'
    mid_source = file_source
    found = False
    message = ""
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_url, mid_number, file_end, mid_eir, mid_source, file_source, file_big, file_small)
                   for mid_number in range(mid_number_start, mid_number_end)]
        for future in futures:
            mid_number, status_code, url_info, response_text = future.result()
            if status_code == 200:
                try:
                    image_json = json.loads(response_text)
                    max_width = image_json['width']
                    max_height = image_json['height']
                    max_mp = round(max_width * max_height / 10**6, 1)
                    message += f'Found image at {url_info}\n'
                    message += f'Image is {max_width}x{max_height} = {max_mp}MP\n'
                except Exception as e:
                    message += f"Error parsing image JSON: {e}\n"
                    continue

                mid_file = f'{file_source}_{file_big}_{file_small}{file_end}'
                download_msg = download_image(url_info, mid_file, preview)
                message += download_msg
                found = True
                break

    if not found:
        message += "\nNo image found with the provided parameters."
    return found, message

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file_source = request.form.get("file_source")
        file_big = request.form.get("file_big")
        file_small = request.form.get("file_small")
        file_sheet = request.form.get("sheet", "")
        file_part = request.form.get("part", "1")
        mid_number_start = int(request.form.get("start", 1))
        mid_number_end = int(request.form.get("end", 200))
        preview = (request.form.get("preview") == "on")
        
        found, result_message = search_and_download(file_source, file_big, file_small, file_sheet, file_part, mid_number_start, mid_number_end, preview)
        flash(result_message, "info")
        return redirect(url_for("index"))
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
