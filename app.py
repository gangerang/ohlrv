#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import requests, json, subprocess, logging, os, zipfile, uuid, csv, re
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "default_secret_for_dev")

# Configure logging with debug output.
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

@app.before_request
def log_request_info():
    logging.info(f"Incoming request: {request.method} {request.url}")
    # Uncomment the next line for full header details:
    # logging.debug(f"Headers: {dict(request.headers)}")
    if request.method == "POST":
        logging.debug(f"Form Data: {request.form}")

# Register a custom filter to URL‑encode strings.
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

# Load miscellaneous mapping from a JSON file.
MISCELLANEOUS_MAPPING = {}
mapping_file = os.path.join(os.path.dirname(__file__), "static", "data", "miscellaneous_mapping.json")
if os.path.exists(mapping_file):
    with open(mapping_file, "r") as f:
        MISCELLANEOUS_MAPPING = json.load(f)
else:
    logging.warning("Mapping file miscellaneous_mapping.json not found.")

# Function to clean the plan_small_number
def clean_plan_small_number(plan_small_number):
    return re.sub(r'P\d+$', '', plan_small_number)

# Load crown plans data from CSV
CROWN_PLANS_DATA = {}
csv_file_path = os.path.join(os.path.dirname(__file__), "static", "data", "crown_plans.csv")
with open(csv_file_path, mode='r') as csv_file:
    csv_reader = csv.DictReader(csv_file)
    for row in csv_reader:
        cleaned_small_number = clean_plan_small_number(row['plan_small_number'])
        key = f"{row['plan_type']}-{row['plan_big_number']}-{cleaned_small_number}"
        if key not in CROWN_PLANS_DATA:
            CROWN_PLANS_DATA[key] = {'titles': [], 'dates': []}
        CROWN_PLANS_DATA[key]['titles'].append(row['title'])
        if 'created_date' in row and row['created_date']:
            date_str = f"{row['created_date'][:4]}-{row['created_date'][4:6]}-{row['created_date'][6:]}"
            CROWN_PLANS_DATA[key]['dates'].append(date_str)

# Global cache for search results (to avoid oversized session cookies)
SEARCH_RESULTS_CACHE = {}

# Static query size for all searches
QUERY_SIZE = 10000

FILES_DIR = os.path.join(os.path.dirname(__file__), "files")
IMAGES_DIR = os.path.join(FILES_DIR, "images")
MANIFESTS_DIR = os.path.join(FILES_DIR, "manifests")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(MANIFESTS_DIR, exist_ok=True)

# ---------------------------
# General Search Route (Landing Page)
# ---------------------------
@app.route("/", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        # The form handles DP, Vol Fol, Crown Plans, and Parish searches.
        search_type = request.form.get("search_type")  # expected: "dp", "volfol", "crown", or "parish"
        logging.debug(f"Landing Search: search_type={search_type}")
        
        # -------- DP Search --------
        if search_type == "dp":
            dp_number = request.form.get("dp_number", "").strip()
            logging.debug(f"DP Search: dp_number={dp_number}")
            if not dp_number:
                flash("Please enter a DP number.", "danger")
                return redirect(url_for("search"))
            try:
                dp_int = int(dp_number)
            except Exception as e:
                flash("DP number must be numeric.", "danger")
                return redirect(url_for("search"))
            pref_payload = {"preference": "attributeSearch"}
            main_query = {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "must": [
                                    {
                                        "bool": {
                                            "should": [
                                                {"multi_match": {"query": str(dp_int), "fields": ["dpNumber.keyword"], "type": "best_fields", "operator": "or", "fuzziness": 0}},
                                                {"multi_match": {"query": str(dp_int), "fields": ["dpNumber.keyword"], "type": "phrase_prefix", "operator": "or"}}
                                            ],
                                            "minimum_should_match": "1"
                                        }
                                    },
                                    {"match_all": {}}
                                ]
                            }
                        }
                    ]
                }
            }
            query_payload = {"query": main_query, "size": QUERY_SIZE}

        # -------- Vol Fol Search --------
        elif search_type == "volfol":
            # Change here: use "search_str" since that’s what the form uses.
            volfol = request.form.get("search_str", "").strip()
            logging.debug(f"Vol Fol Search: volfol={volfol}")
            if not volfol:
                flash("Please enter a Vol Fol value.", "danger")
                return redirect(url_for("search"))
            pref_payload = {"preference": "attributeSearch"}
            main_query = {
                "bool": {
                    "must": [
                        {"multi_match": {"query": volfol, "fields": ["volFol.lowercase"], "type": "best_fields", "operator": "or", "fuzziness": 0}},
                        {"multi_match": {"query": volfol, "fields": ["volFol.lowercase"], "type": "phrase_prefix", "operator": "or"}}
                    ],
                    "filter": [
                        {"term": {"collectionId": 30}}
                    ]
                }
            }
            query_payload = {"query": main_query, "size": QUERY_SIZE}

        # -------- Crown Plans Search --------
        elif search_type == "crown":
            # For Crown Plans, the form may provide a crown plan number (optional) and optionally county and/or parish.
            crown_number = request.form.get("search_str", "").strip()
            county = request.form.get("county", "").strip()
            parish = request.form.get("parish", "").strip()
            source_option = request.form.get("source_option", "all").strip()  # Options: all, BS, SR
            logging.debug(f"Crown Search: crown_number={crown_number}, county={county}, parish={parish}, source_option={source_option}")
            # At least one field must be provided.
            if not (crown_number or county or parish):
                flash("Please enter at least a Crown Plan number or county/parish.", "danger")
                return redirect(url_for("search"))
            
            # Check for miscellaneous reference code and convert to small number
            crown_parts = crown_number.split(" ")
            if len(crown_parts) == 2 and crown_parts[1].lower() in MISCELLANEOUS_MAPPING:
                crown_number = f"{crown_parts[0]}-{MISCELLANEOUS_MAPPING[crown_parts[1].lower()]['code']}"
            
            pref_payload = {"preference": "attributeSearch"}
            must_clauses = []
            if crown_number:
                must_clauses.extend([
                    {"multi_match": {"query": crown_number, "fields": ["crownPlanNumber"], "type": "best_fields", "operator": "or", "fuzziness": 0}},
                    {"multi_match": {"query": crown_number, "fields": ["crownPlanNumber"], "type": "phrase_prefix", "operator": "or"}}
                ])
            if county:
                must_clauses.append(
                    {"multi_match": {"query": county, "fields": ["countyName.lowercase"], "type": "best_fields", "operator": "or"}}
                )
            if parish:
                must_clauses.append(
                    {"multi_match": {"query": parish, "fields": ["parishName.lowercase"], "type": "best_fields", "operator": "or"}}
                )
            main_query = {"bool": {"must": must_clauses}}
            if source_option.lower() == "bs":
                allowed_ids = [31]
            elif source_option.lower() == "sr":
                allowed_ids = [55]
            else:
                allowed_ids = [31, 55]
            main_query["bool"]["filter"] = [{"terms": {"collectionId": allowed_ids}}]
            query_payload = {"query": main_query, "size": QUERY_SIZE}

        # -------- Parish Search --------
        elif search_type == "parish":
            county = request.form.get("county", "").strip()
            parish = request.form.get("parish", "").strip()
            logging.debug(f"Parish Search: county={county}, parish={parish}")
            if not (county or parish):
                flash("Please enter a county and/or parish.", "danger")
                return redirect(url_for("search"))
            pref_payload = {"preference": "attributeSearch"}
            must_clauses = []
            if county:
                must_clauses.append({"multi_match": {"query": county, "fields": ["countyName.lowercase"], "type": "best_fields", "operator": "or"}})
            if parish:
                must_clauses.append({"multi_match": {"query": parish, "fields": ["parishName.lowercase"], "type": "best_fields", "operator": "or"}})
            main_query = {"bool": {"must": must_clauses}}
            main_query["bool"]["filter"] = [{"terms": {"collectionId": [41,38,40,39,11,12,14,3,15,16,6,9,10,4,13,5,7,8,28,23,26,29,24,27,25,18,21,32,19,33,20]}}]
            query_payload = {"query": main_query, "size": QUERY_SIZE}
        
        else:
            flash("Unknown search type.", "danger")
            return redirect(url_for("search"))
        
        payload = json.dumps(pref_payload) + "\n" + json.dumps(query_payload) + "\n"
        logging.debug(f"Payload: {payload}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Accept": "application/json",
            "Content-Type": "application/x-ndjson",
            "x-portal-token": ""
        }
        url = "https://api.lrsnative.com.au/hlrv/documents/_msearch?"
        try:
            logging.info(f"{search_type.capitalize()} Search: Executing search with payload: {payload}")
            api_response = requests.post(url, headers=headers, data=payload, timeout=10)
            api_response.raise_for_status()
            results = api_response.json()
            documents = results.get("responses", [])[0].get("hits", {}).get("hits", [])
            if not documents:
                flash("No records found for the search query.", "warning")
                return redirect(url_for("search"))
            logging.debug(f"Search results JSON: {json.dumps(documents)}")

            # Add title and created_date information to crown plan search results
            if search_type == "crown":
                for doc in documents:
                    source = doc.get("_source", {})
                    plan_number = source.get("crownPlanNumber", "")
                    plan_type = "SR" if source.get("sourceOffice") == "STATE RECORDS" else "BS"
                    plan_parts = plan_number.split("-")
                    if len(plan_parts) == 2:
                        plan_big_number, plan_small_number = plan_parts
                        cleaned_small_number = clean_plan_small_number(plan_small_number)
                        key = f"{plan_type}-{plan_big_number}-{cleaned_small_number}"
                        if key in CROWN_PLANS_DATA:
                            source["title"] = "\n".join(CROWN_PLANS_DATA[key]['titles'])
                            source["created_date"] = "\n".join(CROWN_PLANS_DATA[key]['dates'])
                        else:
                            source["title"] = "No title available"
                            source["created_date"] = ""

            result_key = str(uuid.uuid4())
            SEARCH_RESULTS_CACHE[result_key] = documents
            session["search_results_key"] = result_key
            session["search_type"] = search_type
            if search_type == "parish":
                return render_template("search_results.html", documents=documents, search_type=search_type, collection_mapping=COLLECTION_MAPPING)
            else:
                return render_template("search_results.html", documents=documents, search_type=search_type)
        except Exception as e:
            logging.error(f"Error during {search_type.capitalize()} search: {e}")
            flash(f"Error during search: {e}", "danger")
            return redirect(url_for("search"))
    return render_template("search.html")

# ---------------------------
# Download Selected Documents Route
# ---------------------------
@app.route("/download_selected", methods=["POST"])
def download_selected():
    selected_ids = request.form.getlist("selected")
    logging.debug(f"Selected IDs: {selected_ids}")
    if not selected_ids:
        flash("No documents selected for download.", "warning")
        return redirect(url_for("search"))
    result_key = session.get("search_results_key")
    logging.debug(f"Session search_results_key: {result_key}")
    if not result_key or result_key not in SEARCH_RESULTS_CACHE:
        flash("Session expired. Please search again.", "danger")
        return redirect(url_for("search"))
    documents = SEARCH_RESULTS_CACHE[result_key]
    logging.debug(f"Documents from cache: {json.dumps(documents)}")
    selected_documents = [doc for doc in documents if doc.get("_id") in selected_ids]
    logging.debug(f"Selected documents: {selected_documents}")
    if not selected_documents:
        logging.debug("No matching documents found")
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
                location = image.get("location")
                fileName = image.get("fileName")
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
                temp_manifest = os.path.join(MANIFESTS_DIR, f"manifest_{doc_id}_{fileName}.json")
                with open(temp_manifest, "w") as f:
                    f.write(manifest_modified)
                output_filename = os.path.join(IMAGES_DIR, fileName.replace('.jp2', '.jpg'))
                if not os.path.exists(output_filename):
                    result = subprocess.run([PATH_DEZOOMIFY, '-l', temp_manifest, output_filename, '--logging', 'debug'], capture_output=True)
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
        zip_filename = os.path.join(FILES_DIR, "downloaded_images.zip")
        with zipfile.ZipFile(zip_filename, "w") as zipf:
            for file in downloaded_files:
                zipf.write(file, os.path.basename(file))
        response = send_file(zip_filename, as_attachment=True)
        def cleanup():
            os.remove(zip_filename)
            for file in downloaded_files:
                os.remove(file)
        response.call_on_close(cleanup)
        return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
