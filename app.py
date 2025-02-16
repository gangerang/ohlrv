#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import requests, json, subprocess, logging, os, zipfile
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "default_secret_for_dev")

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

@app.before_request
def log_request_info():
    logging.info(f"Incoming request: {request.method} {request.url}")
    logging.debug(f"Headers: {dict(request.headers)}")
    if request.method == "POST":
        logging.debug(f"Form Data: {request.form}")

# Register a custom filter to URL-encode strings.
app.jinja_env.filters['custom_quote'] = lambda s: quote(s, safe='')

# Path to the dezoomify executable.
PATH_DEZOOMIFY = '/usr/local/bin/dezoomify-rs'

# Load collection mapping from a JSON file.
COLLECTION_MAPPING = {}
mapping_file = os.path.join(os.path.dirname(__file__), "collection_type_name.json")
if os.path.exists(mapping_file):
    with open(mapping_file, "r") as f:
        raw_mapping = json.load(f)
        COLLECTION_MAPPING = {int(k): v for k, v in raw_mapping.items()}
else:
    logging.warning("Mapping file collection_type_name.json not found.")

# ---------------------------
# General Search Route
# ---------------------------
@app.route("/", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        search_str = request.form.get("search_str")
        search_type = request.form.get("search_type", "crown")  # "crown", "volfol", or "parish"
        collection_ids = request.form.get("collection_ids", "").strip()

        if not search_str:
            flash("Please provide a search term.", "danger")
            return redirect(url_for("search"))

        if search_type == "volfol":
            query = search_str
            field_name = "volFol.lowercase"
            query_size = 20
        elif search_type == "parish":
            query = search_str
            field_name = "parishName.lowercase"
            query_size = 10000
        else:
            query = f"CROWN PLAN {search_str}"
            field_name = "imageName.lowercase"
            query_size = 20

        pref_payload = {"preference": "attributeSearch"}
        main_query = {
            "bool": {
                "must": [
                    {
                        "bool": {
                            "must": {
                                "bool": {
                                    "should": [
                                        {"multi_match": {"query": query, "fields": [field_name], "type": "best_fields", "operator": "or", "fuzziness": 0}},
                                        {"multi_match": {"query": query, "fields": [field_name], "type": "phrase_prefix", "operator": "or"}}
                                    ],
                                    "minimum_should_match": 1
                                }
                            }
                        }
                    }
                ]
            }
        }

        if search_type == "parish":
            main_query["bool"]["filter"] = [{
                "terms": {"collectionId": [51,66,36,41,38,40,39,11,12,14,3,15,16,6,9,10,4,13,5,7,8,28,23,26,29,24,27,25,18,21,32,19,33,20]}
            }]
        elif collection_ids:
            try:
                collections = [int(x.strip()) for x in collection_ids.split(",") if x.strip()]
                main_query["bool"]["filter"] = [{"terms": {"collectionId": collections}}]
            except Exception as e:
                flash("Invalid collection IDs. Please use comma-separated numeric values.", "danger")
                return redirect(url_for("search"))

        query_payload = {"query": main_query, "size": query_size}
        payload = json.dumps(pref_payload) + "\n" + json.dumps(query_payload) + "\n"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Accept": "application/json",
            "Content-Type": "application/x-ndjson",
            "x-portal-token": ""
        }
        url = "https://api.lrsnative.com.au/hlrv/documents/_msearch?"
        try:
            logging.info(f"Searching for: {query} (type: {search_type})")
            api_response = requests.post(url, headers=headers, data=payload, timeout=10)
            api_response.raise_for_status()
            results = api_response.json()
            documents = results.get("responses", [])[0].get("hits", {}).get("hits", [])
            if not documents:
                flash("No documents found for the search query.", "warning")
                return redirect(url_for("search"))
            session["search_results_json"] = json.dumps(documents)
            session["search_type"] = search_type
            if search_type == "parish":
                return render_template("search_results.html", documents=documents, search_type=search_type, collection_mapping=COLLECTION_MAPPING)
            else:
                return render_template("search_results.html", documents=documents, search_type=search_type)
        except Exception as e:
            logging.error(f"Error during search: {e}")
            flash(f"Error during search: {e}", "danger")
            return redirect(url_for("search"))
    return render_template("search.html")


# ---------------------------
# New "Search within Parish" Route
# ---------------------------
@app.route("/search_within_parish", methods=["POST"])
def search_within_parish():
    county = request.form.get("county", "").strip()
    parish = request.form.get("parish", "").strip()
    collection_group = request.form.get("collection_group", "").strip()  # Expected: crown, parish, torrens

    if not parish:
        flash("Please select a parish.", "danger")
        return redirect(url_for("search"))

    # Determine allowed collection IDs based on collection group.
    if collection_group == "crown":
        allowed_ids = [55, 31]
    elif collection_group == "torrens":
        allowed_ids = [30]
    else:  # "parish" group
        allowed_ids = [41,38,40,39,11,12,14,3,15,16,6,9,10,4,13,5,7,8,28,23,26,29,24,27,25,18,21,32,19,33,20]

    pref_payload = {"preference": "attributeSearch"}
    main_query = {
        "bool": {
            "must": [
                {
                    "bool": {
                        "must": {
                            "bool": {
                                "should": [
                                    {"multi_match": {"query": parish, "fields": ["parishName.lowercase"], "type": "best_fields", "operator": "or", "fuzziness": 0}},
                                    {"multi_match": {"query": parish, "fields": ["parishName.lowercase"], "type": "phrase_prefix", "operator": "or"}}
                                ],
                                "minimum_should_match": 1
                            }
                        }
                    }
                }
            ],
            "filter": [
                {"terms": {"collectionId": allowed_ids}}
            ]
        }
    }
    # Change size from 20 to 10000
    query_payload = {"query": main_query, "size": 10000}
    payload = json.dumps(pref_payload) + "\n" + json.dumps(query_payload) + "\n"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Accept": "application/json",
        "Content-Type": "application/x-ndjson",
        "x-portal-token": ""
    }
    url = "https://api.lrsnative.com.au/hlrv/documents/_msearch?"
    try:
        logging.info(f"Searching within parish: {parish} (county: {county}) with collection group: {collection_group}")
        api_response = requests.post(url, headers=headers, data=payload, timeout=10)
        api_response.raise_for_status()
        results = api_response.json()
        documents = results.get("responses", [])[0].get("hits", {}).get("hits", [])
        if not documents:
            flash("No documents found for the selected parish.", "warning")
            return redirect(url_for("search"))
        session["search_results_json"] = json.dumps(documents)
        session["search_type"] = "parish"
        return render_template("search_results.html", documents=documents, search_type="parish", collection_mapping=COLLECTION_MAPPING)
    except Exception as e:
        logging.error(f"Error in search_within_parish: {e}")
        flash(f"Error during search: {e}", "danger")
        return redirect(url_for("search"))

###############################################################################
# Download Selected Documents Route (unchanged)
###############################################################################
@app.route("/download_selected", methods=["POST"])
def download_selected():
    selected_ids = request.form.getlist("selected")
    if not selected_ids:
        flash("No documents selected for download.", "warning")
        return redirect(url_for("search"))
    documents_json = session.get("search_results_json")
    if not documents_json:
        flash("Session expired. Please search again.", "danger")
        return redirect(url_for("search"))
    documents = json.loads(documents_json)
    selected_documents = [doc for doc in documents if doc.get("_id") in selected_ids]
    if not selected_documents:
        flash("No matching documents found.", "danger")
        return redirect(url_for("search"))
    
    downloaded_files = []
    for doc in selected_documents:
        source = doc.get("_source", {})
        doc_id = doc.get("_id")
        logging.info(f"Downloading document {doc_id}: {source.get('countyName')} - {source.get('parishName')}, "
                     f"Location: {source.get('location')}, Date: {source.get('dateCreated')}")
        images = source.get("images", [])
        for image in images:
            try:
                location = image.get("location")  # e.g., "eirCP/BS/1-100/15"
                fileName = image.get("fileName")   # e.g., "BS_650_1538J1.jp2"
                # Build the full path (must include "eirCP/").
                path = f"{location}/{fileName}"
                encoded = quote(path, safe='')
                info_url = f"https://api.lrsnative.com.au/hlrv/iiif/2/{encoded}/info.json"
                logging.info(f"Fetching manifest for document {doc_id}, image {fileName} from {info_url}")
                manifest_response = requests.get(info_url, timeout=10)
                manifest_response.raise_for_status()
                manifest = manifest_response.text
                image_json = json.loads(manifest)
                if "profile" in image_json and isinstance(image_json["profile"], list) and len(image_json["profile"]) >= 2:
                    image_json["profile"][0] = "http://iiif.io/api/image/2/level1.json"
                    if isinstance(image_json["profile"][1], dict) and "formats" in image_json["profile"][1]:
                        image_json["profile"][1]["formats"] = ["jpg"]
                manifest_modified = json.dumps(image_json)
                temp_manifest = f"/tmp/manifest_{doc_id}_{fileName}.json"
                with open(temp_manifest, "w") as f:
                    f.write(manifest_modified)
                # Save the file using only the image file name.
                output_filename = fileName.replace('.jp2','.jpg')
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

###############################################################################
# Legacy Version Route (accessible at "/old")
###############################################################################
@app.route("/old", methods=["GET", "POST"])
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
