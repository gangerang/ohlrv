#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash
import requests, json, subprocess, logging, os, sys
from urllib.parse import quote

# Import the iiif_downloader module.
# Make sure the iiif_downloader.py file from https://github.com/ecoto/iiif_downloader is in your project directory.
import iiif_downloader

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET"  # Change for production

# Configure logging: timestamp, level, and message.
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

# URL construction functions.
def construct_url(file_source, mid_range, mid_number, filename):
    """
    Constructs the IIIF info URL by building a path segment and percent‑encoding it.
    For example, the segment:
      eirCP/BS/1-100/15/BS_650_1538J1.jp2
    becomes:
      eirCP%2FBS%2F1-100%2F15%2FBS_650_1538J1.jp2
    and the final URL is:
      https://api.lrsnative.com.au/hlrv/iiif/2/eirCP%2FBS%2F1-100%2F15%2FBS_650_1538J1.jp2/info.json
    """
    path_segment = f"eirCP/{file_source}/{mid_range}/{mid_number}/{filename}.jp2"
    encoded_segment = quote(path_segment, safe='')  # Encode all characters.
    url = f"https://api.lrsnative.com.au/hlrv/iiif/2/{encoded_segment}/info.json"
    logging.debug(f"Constructed info URL: {url}")
    return url

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
    # Calculate mid_range (e.g., "1-100", "101-200", etc.)
    mid_range = f'{((mid_number - 1) // 100) * 100 + 1}-{(((mid_number - 1) // 100) + 1) * 100}'
    filename = f'{file_source}_{file_big}_{file_small}{file_end}'
    url_info = construct_url(file_source, mid_range, mid_number, filename)
    logging.info(f"Fetching info for mid_number {mid_number} from URL: {url_info}")
    try:
        response = requests.get(url_info, verify=True, timeout=10)
        logging.info(f"Received HTTP status {response.status_code} for mid_number {mid_number}")
    except Exception as e:
        logging.error(f"Error fetching URL for mid_number {mid_number}: {e}")
        return mid_number, 0, url_info, ""
    return mid_number, response.status_code, url_info, response.text

def download_image(url_info, mid_file, preview, preview_only, file_source, file_big, file_small, file_end, mid_number):
    # Calculate mid_range for preview URL construction.
    mid_range = f'{((mid_number - 1) // 100) * 100 + 1}-{(((mid_number - 1) // 100) + 1) * 100}'
    if preview:
        preview_url = construct_preview_url(file_source, mid_range, mid_number, f'{file_source}_{file_big}_{file_small}{file_end}')
        logging.info(f"Preview URL for mid_number {mid_number}: {preview_url}")
        flash(f'Preview image: <a href="{preview_url}" target="_blank">{preview_url}</a>', 'info')
    if preview_only:
        logging.info(f"Preview only mode: skipping download for {mid_file}.jpg")
        return f"Preview only mode: skipping download for {mid_file}.jpg<br>"
    
    # Use iiif_downloader directly via its Python API.
    # The command-line usage is:
    #   python iiif_downloader.py iif_document_url images_base_path [-m metadata_file_path] [-w image_max_width] [-c]
    # We simulate that by constructing a list of arguments.
    download_dir = "/tmp/iiif_downloader_images"
    os.makedirs(download_dir, exist_ok=True)
    logging.info(f"Using download directory: {download_dir}")
    
    # Build the argument list.
    # Here, url_info is the manifest URL, and download_dir is where images will be stored.
    # Adjust the flags (-w, -c) as needed.
    args = ["iiif_downloader.py", url_info, download_dir, "-w", "2500", "-c"]
    logging.info(f"Calling iiif_downloader with arguments: {args}")
    
    # Temporarily override sys.argv and call the main() of iiif_downloader.
    old_argv = sys.argv
    sys.argv = args
    try:
        iiif_downloader.main()  # This will perform the download.
    except Exception as e:
        logging.error(f"Error during iiif_downloader.main() call: {e}")
        sys.argv = old_argv
        return f"Error during iiif_downloader execution: {e}<br>"
    sys.argv = old_argv
    
    # List contents of the download directory.
    try:
        files = os.listdir(download_dir)
        logging.debug(f"Contents of download directory: {files}")
    except Exception as e:
        logging.error(f"Error listing download directory: {e}")
        files = []
    
    jpg_files = [f for f in files if f.lower().endswith('.jpg')]
    if not jpg_files:
        logging.error("No .jpg file found in download directory")
        return "iiif_downloader did not produce any jpg file<br>"
    output_file = os.path.join(download_dir, jpg_files[0])
    
    # Move (rename) the output file to the desired filename.
    desired_file = f"{mid_file}.jpg"
    try:
        os.rename(output_file, desired_file)
        logging.info(f"Moved downloaded file from {output_file} to {desired_file}")
    except Exception as e:
        logging.error(f"Error moving file: {e}")
        return f"Error moving downloaded file: {e}<br>"
    
    return f"Image successfully saved to {desired_file}<br>"

def search_and_download(file_source, file_big, file_small, file_end, start_number, end_number, preview, preview_only):
    found = False
    message = ""
    logging.info(f"Starting search_and_download with file_source={file_source}, file_big={file_big}, file_small={file_small}, file_end={file_end}, start_number={start_number}, end_number={end_number}, preview={preview}, preview_only={preview_only}")
    # Loop through candidate mid_numbers.
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
                # Use the info JSON as received.
            except Exception as e:
                logging.error(f"Error parsing JSON for mid_number {mid_number}: {e}")
                message += f"Error parsing JSON for mid_number {mid_number}: {str(e)}<br>"
                continue
            mid_file = f'{file_source}_{file_big}_{file_small}{file_end}'
            message += download_image(url_info, mid_file, preview, preview_only,
                                      file_source, file_big, file_small, file_end, mid_number)
            found = True
            break
        else:
            logging.debug(f"mid_number {mid_number} returned status {status_code}")
    if not found:
        message += "No image found with the provided parameters.<br>"
        logging.warning("Search completed: no valid image found.")
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
        found, message = search_and_download(file_source, file_big, file_small, file_end,
                                             start_number, end_number, preview, preview_only)
        if not found:
            message += "No results found with provided parameters. "
            logging.warning("No results found with provided parameters.")
        flash(message, 'info')
        return redirect(url_for("index"))
    return render_template("index.html")

if __name__ == "__main__":
    logging.info("Starting Flask app")
    app.run(host="0.0.0.0", port=5000, debug=True)
