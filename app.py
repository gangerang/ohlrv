#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import requests, json, subprocess, logging, os, time
from urllib.parse import quote

app = Flask(__name__)

# Configure logging to output timestamp, log level, and message.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Log each incoming request.
@app.before_request
def log_request_info():
    logging.info(f"Incoming request: {request.method} {request.url}")
    logging.debug(f"Headers: {dict(request.headers)}")
    if request.method == "POST":
        logging.debug(f"Form Data: {request.form}")

# Path to the dezoomify executable.
PATH_DEZOOMIFY = '/usr/local/bin/dezoomify-rs'

# Mapping dictionary.
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

# Construct the info.json URL by encoding the IIIF image path.
def construct_url(file_source, mid_range, mid_number, filename):
    path_segment = f"eirCP/{file_source}/{mid_range}/{mid_number}/{filename}.jp2"
    encoded_segment = quote(path_segment, safe='')  # encode all characters.
    url = f"https://api.lrsnative.com.au/hlrv/iiif/2/{encoded_segment}/info.json"
    logging.debug(f"Constructed info URL: {url}")
    return url

# Construct the preview URL.
def construct_preview_url(file_source, mid_range, mid_number, filename):
    path_segment = f"eirCP/{file_source}/{mid_range}/{mid_number}/{filename}.jp2"
    encoded_segment = quote(path_segment, safe='')
    url = f"https://api.lrsnative.com.au/hlrv/iiif/2/{encoded_segment}/full/1024,/0/default.jpg"
    logging.debug(f"Constructed preview URL: {url}")
    return url

def get_small_number(ms):
    num = MS_MAPPING.get(ms, {}).get('number')
    logging.debug(f"get_small_number({ms}) returned {num}")
    return num

def fetch_url(mid_number, file_source, file_big, file_small, file_end):
    mid_range = f'{((mid_number - 1) // 100) * 100 + 1}-{(((mid_number - 1) // 100) + 1) * 100}'
    base_filename = f'{file_source}_{file_big}_{file_small}{file_end}'
    url_info = construct_url(file_source, mid_range, mid_number, base_filename)
    logging.info(f"Fetching info for mid_number {mid_number} from URL: {url_info}")
    try:
        response = requests.get(url_info, verify=True, timeout=10)
        logging.info(f"Received HTTP status {response.status_code} for mid_number {mid_number}")
    except Exception as e:
        logging.error(f"Error fetching URL for mid_number {mid_number}: {e}")
        return mid_number, 0, url_info, ""
    return mid_number, response.status_code, url_info, response.text

def download_image(url_info, mid_file_base, preview, preview_only, file_source, file_big, file_small, file_end, mid_number, manifest_text):
    mid_range = f'{((mid_number - 1) // 100) * 100 + 1}-{(((mid_number - 1) // 100) + 1) * 100}'
    if preview:
        preview_url = construct_preview_url(file_source, mid_range, mid_number, f'{file_source}_{file_big}_{file_small}{file_end}')
        logging.info(f"Preview URL for mid_number {mid_number}: {preview_url}")
        flash(f'Preview image: <a href="{preview_url}" target="_blank">{preview_url}</a>', 'info')
    if preview_only:
        logging.info(f"Preview only mode: skipping download for {mid_file_base}.jpg")
        return None, f"Preview only mode: skipping download for {mid_file_base}.jpg<br>"
    
    # Generate a Unix timestamp rounded to the nearest 10 seconds.
    timestamp = str(round(time.time() / 10) * 10)
    desired_file = f"{mid_file_base}_{timestamp}.jpg"
    
    temp_manifest = f"/tmp/manifest_{mid_number}.json"
    try:
        with open(temp_manifest, "w") as f:
            f.write(manifest_text)
        abs_manifest = os.path.abspath(temp_manifest)
        if not os.path.exists(abs_manifest):
            raise Exception(f"Manifest file not found at {abs_manifest}")
        logging.info(f"Manifest file created at: {abs_manifest}")
    except Exception as e:
        logging.error(f"Error writing manifest to {temp_manifest}: {e}")
        return None, f"Error writing manifest: {e}<br>"
    
    logging.info(f"Starting dezoomify for mid_number {mid_number}, saving to {desired_file} using manifest {abs_manifest}")
    result = subprocess.run([PATH_DEZOOMIFY, '-l', abs_manifest, desired_file], capture_output=True)
    if result.returncode != 0:
        error_message = result.stderr.decode()
        logging.error(f"dezoomify error for {desired_file}: {error_message}")
        return None, f'Error during dezoomify execution: {error_message}<br>'
    else:
        logging.info(f"dezoomify succeeded for {desired_file}")
        return desired_file, f'Image successfully saved to {desired_file}<br>'

def search_and_download(file_source, file_big, file_small, file_end, start_number, end_number, preview, preview_only):
    found = False
    message = ""
    downloaded_file = None
    logging.info(f"Starting search_and_download with file_source={file_source}, file_big={file_big}, file_small={file_small}, file_end={file_end}, start_number={start_number}, end_number={end_number}, preview={preview}, preview_only={preview_only}")
    for mid_number in range(start_number, end_number):
        logging.debug(f"Trying mid_number: {mid_number}")
        mid_number, status_code, url_info, response_text = fetch_url(mid_number, file_source, file_big, file_small, file_end)
        if status_code == 200:
            logging.info(f"Valid response received for mid_number {mid_number}")
            try:
                image_json = json.loads(response_text)
                max_width = image_json.get('width')
                max_height = image_json.get('height')
                max_mp = round(max_width * max_height / 10**6, 1)
                message += f"Found image at {url_info}<br>"
                message += f"Image is {max_width}x{max_height} = {max_mp}MP<br>"
                logging.debug(f"Image dimensions: {max_width}x{max_height} ({max_mp}MP)")
                # Modify the manifest JSON as required.
                if "profile" in image_json and isinstance(image_json["profile"], list) and len(image_json["profile"]) >= 2:
                    image_json["profile"][0] = "http://iiif.io/api/image/2/level1.json"
                    if isinstance(image_json["profile"][1], dict) and "formats" in image_json["profile"][1]:
                        image_json["profile"][1]["formats"] = ["jpg"]
                modified_manifest = json.dumps(image_json)
            except Exception as e:
                logging.error(f"Error parsing JSON for mid_number {mid_number}: {e}")
                message += f"Error parsing JSON for mid_number {mid_number}: {str(e)}<br>"
                continue
            mid_file_base = f'{file_source}_{file_big}_{file_small}{file_end}'
            downloaded_file, dl_msg = download_image(url_info, mid_file_base, preview, preview_only,
                                                     file_source, file_big, file_small, file_end, mid_number, modified_manifest)
            message += dl_msg
            if downloaded_file:
                found = True
                break
        else:
            logging.debug(f"mid_number {mid_number} returned status {status_code}")
    if not found:
        message += "No image found with the provided parameters.<br>"
        logging.warning("Search completed: no valid image found.")
    logging.info("Finished search_and_download")
    return found, message, downloaded_file

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
            logging.error("Invalid input: Start and End numbers must be integers.")
            return redirect(url_for("index"))
        preview = (request.form.get("preview") == "on")
        preview_only = (request.form.get("preview_only") == "on")
        file_end = f'P{file_sheet}J{file_part}' if file_sheet else f'J{file_part}'
        logging.info(f"Form data received: file_source={file_source}, file_big={file_big}, file_small={file_small}, sheet={file_sheet}, part={file_part}, start_number={start_number}, end_number={end_number}, preview={preview}, preview_only={preview_only}")
        if not any(char.isdigit() for char in file_small):
            num = get_small_number(file_small)
            if not num:
                flash(f'Invalid Ms: {file_small}. Valid options are: ' + ", ".join(MS_MAPPING.keys()), 'danger')
                logging.error(f"Invalid Ms value: {file_small}")
                return redirect(url_for("index"))
            else:
                file_small = str(num)
                logging.info(f"Converted file_small using MS_MAPPING: {file_small}")
        found, message, downloaded_file = search_and_download(file_source, file_big, file_small, file_end,
                                                              start_number, end_number, preview, preview_only)
        flash(message, 'info')
        if found and downloaded_file:
            response = send_file(downloaded_file, as_attachment=True)
            response.call_on_close(lambda: os.remove(downloaded_file))
            return response
        else:
            return redirect(url_for("index"))
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
