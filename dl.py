#!/usr/bin/env python3
import time
import requests
from pathlib import Path
from PIL import Image

def generate_atari_image_urls(start=1, end=185):
    base_img_url = "https://www.atariarchives.org/basicgames/pages/page"
    return [f"{base_img_url}{page}.gif" for page in range(start, end + 1)]

def convert_to_png(src_path, dest_dir="png_output"):
    """Converts an image file to PNG format using Pillow, saving to dest_dir."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(src_path)
    # Use lossless PNG save
    png_path = dest_dir / (Path(src_path).stem + ".png")
    img.save(png_path, format="PNG", optimize=True)
    print(f"Converted {src_path} -> {png_path}")

def download_images(urls, save_dir="downloads", pause_seconds=1):
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    
    for url in urls:
        filename = url.split("/")[-1]
        save_path = Path(save_dir) / filename

        print(f"Downloading {url} -> {save_path}")
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(response.content)
            # Convert to PNG after download
            convert_to_png(save_path)
        except Exception as e:
            print(f"Failed to download or convert {url}: {e}")
        
        time.sleep(pause_seconds)

def main():
    urls = generate_atari_image_urls()
    download_images(urls)

if __name__ == "__main__":
    main()
