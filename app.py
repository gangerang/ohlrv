#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash
import requests, json, subprocess, logging
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET"  # Change for production

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Path to the dezoomify executable.
# (In Docker, we expect the Linux binary to be at /usr/local/bin/dezoomify-rs)
PATH_DEZOOMIFY = '/usr/local/bin/dezoomify-rs'

# Mapping dictionary
MS_MAPPING = {
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

# URL templates
BASE_URL = 'https://api.lrsnative.com.au/hlrv/iiif/2/eirCP%2F{file_source}%2F{mid_range}%2F{mid_number}%2F{filename}.jp2/info.json'
PREVIEW_URL = 'https://api.lrsnative.com.au/hlrv/iiif/2/eirCP%2F{file_source}%2F{mid_range}%2F{mid_number}%2F{filename}.jp2/full/1024,/0/default.jpg'

def get_small_number(ms):
    num = MS_MAPPING.get(ms, {}).get('number')
    logging.debug(f"get_small_number({ms}) returned {num}")
    return num

def construct_url(file_source, mid_range, mid_number, filename):
    url = BASE_URL.format(
        file_source=file_source,
        mid_range=mid_range,
        mid_number=mid_number,
        filename=filename
    )
    logging.debug(f"Constructed URL: {url}")
    return url

def fetch_url(mid_number, file_source, file_big, file_small, file_end):
    mid_range = f'{((mid_number - 1) // 100) * 100 + 1}-{(((mid_number - 1) // 100) + 1) * 100}'
    filename = f'{file_source}_{file_big}_{file_small}{file_end}'
    url_info = construct_url(file_source, mid_range, mid_number, filename)
    logging.debug(f"Fetching URL for mid_number {mid_number}: {url_info}")
    try:
        # Set a timeout (in seconds) to avoid hanging
        response = requests.get(url_info, verify=True, timeout=10)
        logging.debug(f"Received status {response.status_code} for mid_number {mid_number}")
    except Exception as e:
        logging.error(f"Error fetching URL for mid_number {mid_number}: {e}")
        return mid_number, 0, url_info, ""
    return mid_number, response.status_code, url_info, response.text

def download_image(url_info, mid_file, preview, file_source, file_big, file_small, file_end, mid_number):
    mid_range = f'{((mid_number - 1) // 100) * 100 + 1}-{(((mid_number - 1) // 100) + 1) * 100}'
    if preview:
        preview_url = PREVIEW_URL.format(
            file_source=file_source,
            mid_range=mid_range,
            mid_number=mid_number,
            filename=f'{file_source}_{file_big}_{file_small}{file_end}'
        )
        logging.info(f"Preview URL: {preview_url}")
        flash(f'Preview image: <a href="{preview_url}" target="_blank">{preview_url}</a>', 'info')
    logging.info(f"Starting dezoomify for URL: {url_info}")
    result = subprocess.run([PATH_DEZOOMIFY, '-l', url_info, f'{mid_file}.jpg'], capture_output=True)
    if result.returncode != 0:
        error_message = result.stderr.decode()
        logging.error(f"dezoomify error for {mid_file}.jpg: {error_message}")
        return f'Error during dezoomify execution: {error_message}<br>'
    else:
        logging.info(f"dezoomify succeeded for {mid_file}.jpg")
        return f'Image successfully saved to {mid_file}.jpg<br>'

def search_and_download(file_source, file_big, file_small, file_end, start_number, end_number, preview):
    found = False
    message = ""
    logging.info(f"Starting search_and_download with parameters: file_source={file_source}, file_big={file_big}, file_small={file_small}, file_end={file_end}, start_number={start_number}, end_number={end_number}, preview={preview}")
    for mid_number in range(start_number, end_number):
        logging.debug(f"Trying mid_number: {mid_number}")
        mid_number, status_code, url_info, response_text = fetch_url(mid_number, file_source, file_big, file_small, file_end)
        if status_code == 200:
            logging.info(f"Found valid response for mid_number {mid_number}")
            try:
                image_json = json.loads(response_text)
                max_width = image_json.get('width')
                max_height = image_json.get('height')
                max_mp = round(max_width * max_height / 10**6, 1)
                message += f"Found image at {url_info}<br>"
                message += f"Image is {max_width}x{max_height} = {max_mp}MP<br>"
                logging.debug(f"Image dimensions for mid_number {mid_number}: {max_width}x{max_height} = {max_mp}MP")
            except Exception as e:
                logging.error(f"Error parsing JSON for mid_number {mid_number}: {e}")
                message += f"Error parsing JSON for mid_number {mid_number}: {e}<br>"
                continue
            mid_file = f'{file_source}_{file_big}_{file_small}{file_end}'
            message += download_image(url_info, mid_file, preview, file_source, file_big, file_small, file_end, mid_number)
            found = True
            break
        else:
            logging.debug(f"mid_number {mid_number} returned status {status_code}")
    if not found:
        message += "No image found with the provided parameters.<br>"
    logging.info("Finished search_and_download")
    return found, message

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file_source = request.form.get("file_source")
        file_big = request.form.get("file_big")
        file_small = request.form.get("file_small")
        file_sheet = request.form.get("sheet", "")
        file_part = request.form.get("part", "1")
        try:
            start_number = int(request.form.get("start", 1))
            end_number = int(request.form.get("end", 200))
        except ValueError:
            flash("Start and End numbers must be integers.", "danger")
            return redirect(url_for("index"))
        preview = (request.form.get("preview") == "on")
        file_end = f'P{file_sheet}J{file_part}' if file_sheet else f'J{file_part}'
        logging.info(f"Received form data: file_source={file_source}, file_big={file_big}, file_small={file_small}, file_sheet={file_sheet}, file_part={file_part}, start_number={start_number}, end_number={end_number}, preview={preview}")
        if not any(char.isdigit() for char in file_small):
            num = get_small_number(file_small)
            if not num:
                flash(f'Invalid Ms: {file_small}. Valid options are: ' + ", ".join(MS_MAPPING.keys()), 'danger')
                return redirect(url_for("index"))
            else:
                file_small = str(num)
                logging.info(f"Converted file_small using MS_MAPPING: {file_small}")
        found, message = search_and_download(file_source, file_big, file_small, file_end, start_number, end_number, preview)
        if not found:
            message += "No results found with provided parameters. "
            logging.warning("No results found in search_and_download")
        flash(message, 'info')
        return redirect(url_for("index"))
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
