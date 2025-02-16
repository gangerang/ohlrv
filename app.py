#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import requests, json, subprocess, logging, os
from urllib.parse import quote
import zipfile

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "default_secret_for_dev")

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

# --------------
# EXISTING CODE
# --------------
# (your current routes and functions remain available if needed)
# … (existing index route and search_and_download functions) …

# --------------
# NEW SEARCH FUNCTIONALITY
# --------------

@app.route("/search", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        search_str = request.form.get("search_str")
        if not search_str:
            flash("Please provide a search string.", "danger")
            return redirect(url_for("search"))
        query = f"CROWN PLAN {search_str}"
        # Build the NDJSON payload (ensure the format is exactly what the API expects)
        payload = (
            '{"preference":"attributeSearch"}\n'
            '{"query":{"bool":{"must":[{"bool":{"must":{"bool":{"should":['
            '{"multi_match":{"query":"' + query + '","fields":["imageName.lowercase"],'
            '"type":"best_fields","operator":"or","fuzziness":0}},'
            '{"multi_match":{"query":"' + query + '","fields":["imageName.lowercase"],'
            '"type":"phrase_prefix","operator":"or"}}'
            '],"minimum_should_match":"1"}}}}]},"size":20}\n'
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Accept": "application/json",
            "Accept-Language": "en-GB,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-ndjson",
            "Referer": "https://hlrv.nswlrs.com.au/",
            "Origin": "https://hlrv.nswlrs.com.au",
            "Sec-GPC": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "x-portal-token": ""
        }
        url = "https://api.lrsnative.com.au/hlrv/documents/_msearch?"
        try:
            logging.info(f"Searching for: {query}")
            logging.debug(f"Sending POST to {url}\nHeaders: {headers}\nPayload: {payload}")
            api_response = requests.post(url, headers=headers, data=payload, timeout=10)
            api_response.raise_for_status()  # will raise HTTPError for 400+
            results = api_response.json()
            documents = results.get("responses", [])[0].get("hits", {}).get("hits", [])
            if not documents:
                flash("No documents found for the search query.", "warning")
                return redirect(url_for("search"))
            session["search_results_json"] = json.dumps(documents)
            return render_template("search_results.html", documents=documents)
        except requests.exceptions.HTTPError as e:
            # Log additional details about the error
            logging.error(f"HTTP error {api_response.status_code}: {api_response.text}")
            flash(f"HTTP error {api_response.status_code}: {api_response.text}", "danger")
            return redirect(url_for("search"))
        except Exception as e:
            logging.error(f"Error calling external API: {e}")
            flash(f"Error during search: {str(e)}", "danger")
            return redirect(url_for("search"))
    return render_template("search.html")


@app.route("/download_selected", methods=["POST"])
def download_selected():
    """
    Process the selection from the search results page. For each document selected,
    iterate over its image parts, fetch the IIIF manifest, modify it to force jpg output,
    and then call dezoomify-rs to download the image. If more than one file is downloaded,
    create a zip archive.
    """
    selected_ids = request.form.getlist("selected")
    if not selected_ids:
        flash("No documents selected for download.", "warning")
        return redirect(url_for("search"))
    documents_json = session.get("search_results_json")
    if not documents_json:
        flash("Session expired. Please search again.", "danger")
        return redirect(url_for("search"))
    documents = json.loads(documents_json)
    # Filter the documents using the _id field (all are strings in the JSON response)
    selected_documents = [doc for doc in documents if doc.get("_id") in selected_ids]
    if not selected_documents:
        flash("No matching documents found.", "danger")
        return redirect(url_for("search"))
    
    downloaded_files = []
    for doc in selected_documents:
        source = doc.get("_source", {})
        doc_id = doc.get("_id")
        # Log document info (countyName, parishName, location, dateCreated)
        logging.info(f"Downloading document {doc_id}: "
                     f"{source.get('countyName')} - {source.get('parishName')}, "
                     f"Location: {source.get('location')}, Date: {source.get('dateCreated')}")
        images = source.get("images", [])
        for image in images:
            try:
                location = image.get("location")  # e.g., "eirCP/SR/1-100/1"
                fileName = image.get("fileName")   # e.g., "SR_1_369AJ1.jp2"
                # Build the full path. (Note: the API response already includes "eirCP/" in location.)
                path = f"{location}/{fileName}"
                encoded = quote(path, safe='')
                info_url = f"https://api.lrsnative.com.au/hlrv/iiif/2/{encoded}/info.json"
                logging.info(f"Fetching manifest for document {doc_id}, image {fileName} from {info_url}")
                manifest_response = requests.get(info_url, timeout=10)
                manifest_response.raise_for_status()
                manifest = manifest_response.text
                # Modify the manifest so that the image is output as jpg (similar to your original code)
                image_json = json.loads(manifest)
                if "profile" in image_json and isinstance(image_json["profile"], list) and len(image_json["profile"]) >= 2:
                    image_json["profile"][0] = "http://iiif.io/api/image/2/level1.json"
                    if isinstance(image_json["profile"][1], dict) and "formats" in image_json["profile"][1]:
                        image_json["profile"][1]["formats"] = ["jpg"]
                manifest_modified = json.dumps(image_json)
                # Write manifest to a temporary file.
                temp_manifest = f"/tmp/manifest_{doc_id}_{fileName}.json"
                with open(temp_manifest, "w") as f:
                    f.write(manifest_modified)
                # Create a unique output filename (replace .jp2 with .jpg)
                output_filename = f"{doc_id}_{fileName.replace('.jp2','.jpg')}"
                if not os.path.exists(output_filename):
                    result = subprocess.run([PATH_DEZOOMIFY, '-l', temp_manifest, output_filename], capture_output=True)
                    if result.returncode != 0:
                        error_message = result.stderr.decode()
                        logging.error(f"dezoomify error for {output_filename}: {error_message}")
                        flash(f"Error downloading {output_filename}: {error_message}", "danger")
                        continue
                    else:
                        logging.info(f"Downloaded {output_filename}")
                else:
                    logging.info(f"File {output_filename} already exists, reusing it.")
                downloaded_files.append(output_filename)
            except Exception as e:
                logging.error(f"Error downloading image {fileName} from document {doc_id}: {e}")
                flash(f"Error downloading image {fileName} from document {doc_id}: {str(e)}", "danger")
    if not downloaded_files:
        flash("No images were successfully downloaded.", "danger")
        return redirect(url_for("search"))
    # If only one file downloaded, send that file; if multiple, create a zip.
    if len(downloaded_files) == 1:
        file_to_send = downloaded_files[0]
        response = send_file(file_to_send, as_attachment=True)
        response.call_on_close(lambda: os.remove(file_to_send))
        return response
    else:
        zip_filename = "downloaded_images.zip"
        with zipfile.ZipFile(zip_filename, "w") as zipf:
            for file in downloaded_files:
                zipf.write(file)
        response = send_file(zip_filename, as_attachment=True)
        def cleanup():
            os.remove(zip_filename)
            for file in downloaded_files:
                os.remove(file)
        response.call_on_close(cleanup)
        return response

# --------------
# EXISTING INDEX ROUTE (optional)
# --------------

@app.route("/", methods=["GET", "POST"])
def index():
    # You can keep your original form if desired.
    # For example, a link to the new search functionality could be provided here.
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
