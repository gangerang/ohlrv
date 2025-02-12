#!/usr/bin/env python3
"""
iiif_downloader_info.py

A modified downloader that accepts a IIIF Image API info.json URL directly.
It downloads the image at the desired size (or "full" size by default) and saves it as a JPEG.
"""

import argparse
import os
import requests
from PIL import Image

def download_image_from_info(info_url, output_path, image_max_width="full", verify_ssl=False):
    """
    Downloads an image using a IIIF info.json URL.
    
    Parameters:
      info_url (str): URL to the IIIF info.json.
      output_path (str): File path where the downloaded image will be saved.
      image_max_width (str): Either "full" or a numeric value (as string) specifying the max width.
      verify_ssl (bool): Whether to verify the SSL certificate.
    """
    print("Downloading IIIF info from:", info_url)
    r = requests.get(info_url, verify=verify_ssl)
    if r.status_code != 200:
        raise Exception(f"Error fetching info.json: HTTP {r.status_code}")
    
    info = r.json()
    
    # Ensure this looks like an info.json from the IIIF Image API.
    # (It should have an @context like "http://iiif.io/api/image/2/context.json")
    if info.get("@context", "").strip() != "http://iiif.io/api/image/2/context.json":
        raise Exception("The provided URL does not appear to be a valid IIIF info.json")
    
    # The service URL is typically stored in the "@id" field.
    service_url = info.get("@id")
    if not service_url:
        raise Exception("The info.json does not contain an '@id' field")
    
    # Determine the size parameter.
    if image_max_width == "full":
        size = "full"
    else:
        # If a numeric width is provided, use the IIIF API's size format:
        #   e.g., "2500," means width=2500 and height is computed proportionally.
        size = f"{image_max_width},"
    
    # Construct the image URL using the standard IIIF image URL pattern:
    # {service_url}/full/{size}/0/default.jpg
    image_url = f"{service_url}/full/{size}/0/default.jpg"
    print("Downloading image from:", image_url)
    img_response = requests.get(image_url, verify=verify_ssl)
    if img_response.status_code != 200:
        raise Exception(f"Error downloading image: HTTP {img_response.status_code}")
    
    # Save the image bytes to a file.
    with open(output_path, "wb") as f:
        f.write(img_response.content)
    
    # Optionally, open the image with Pillow and re-save as JPEG to ensure format.
    try:
        img = Image.open(output_path)
        rgb_img = img.convert("RGB")
        rgb_img.save(output_path, "JPEG")
        print(f"Image successfully saved to {output_path}")
    except Exception as e:
        print("Image downloaded but error re-saving with Pillow:", e)

def main():
    parser = argparse.ArgumentParser(description="Download image using a IIIF info.json directly")
    parser.add_argument("info_url", help="URL to the IIIF info.json")
    parser.add_argument("output_path", help="File path to save the downloaded image")
    parser.add_argument("-w", "--width", type=str, default="full", help="Max image width (or 'full'); default: full")
    parser.add_argument("-c", "--verify_ssl", action="store_true", help="Enable SSL certificate verification")
    args = parser.parse_args()
    
    download_image_from_info(args.info_url, args.output_path, args.width, args.verify_ssl)

if __name__ == "__main__":
    main()
