#!/usr/bin/env python3
import time
import requests
from pathlib import Path
from PIL import Image
from google import genai
import os

def generate_atari_image_urls(start=1, end=185):
    base_img_url = "https://www.atariarchives.org/basicgames/pages/page"
    return [f"{base_img_url}{page}.gif" for page in range(start, end + 1)]

def convert_to_png(src_path, dest_dir="png_output"):
    """Converts an image file to PNG format using Pillow, saving to dest_dir."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    png_path = dest_dir / (Path(src_path).stem + ".png")
    
    # Check if PNG already exists
    if png_path.exists():
        print(f"PNG already exists: {png_path}")
        return png_path
    
    img = Image.open(src_path)
    img.save(png_path, format="PNG", optimize=True)
    print(f"Converted {src_path} -> {png_path}")
    return png_path

def download_images(urls, save_dir="downloads", pause_seconds=0.5):
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    downloaded_files = []
    for url in urls:
        filename = url.split("/")[-1]
        save_path = Path(save_dir) / filename
        
        # Check if file already exists
        if save_path.exists():
            print(f"File already exists: {save_path}")
        else:
            print(f"Downloading {url} -> {save_path}")
            try:
                response = requests.get(url)
                response.raise_for_status()
                with open(save_path, "wb") as f:
                    f.write(response.content)
            except Exception as e:
                print(f"Failed to download {url}: {e}")
                continue
        
        try:
            png_path = convert_to_png(save_path)
            downloaded_files.append(png_path)
        except Exception as e:
            print(f"Failed to convert {save_path}: {e}")
        
        time.sleep(pause_seconds)
    return downloaded_files

def upload_image_to_gemini(image_path, client):
    file = client.files.upload(file=str(image_path))
    # Poll for upload completion
    while file.state == "PROCESSING":
        print(f"Waiting for upload to complete: {file.state}")
        time.sleep(1)
        file = client.files.get(name=file.name)
    
    if file.state == "FAILED":
        raise Exception(f"File upload failed: {file.name}")
    
    print(f"Upload complete: {file.name} (state: {file.state})")
    return file

def delete_gemini_file(file_name, client):
    client.files.delete(name=file_name)
    print(f"Deleted Gemini file: {file_name}")

def save_transcription_to_markdown(transcription, page_number, output_dir="transcriptions"):
    """Save transcription result to a markdown file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename based on page number
    filename = f"page_{page_number:02d}.md"
    output_path = output_dir / filename
    
    # Write transcription to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(transcription)
    
    print(f"Saved transcription to: {output_path}")
    return output_path

def transcribe_atari_basic(file, client):
    prompt = (
        "Please extract and transcribe all text content from this image, paying special attention to "
        "any BASIC program listings. The image may contain Atari BASIC code with line numbers in a "
        "terminal-like computer typeface. If you find any BASIC programs, please transcribe them "
        "exactly as they appear, maintaining the original formatting and line numbers. If there are "
        "program titles or names, please note them as well. Provide the transcribed content in "
        "markdown format."
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, file]
    )
    return response.text

def main():
    # Download and convert the first 10 images for testing
    urls = generate_atari_image_urls(start=1, end=10)
    png_files = download_images(urls)
    if not png_files:
        print("No images downloaded.")
        return
    
    # Process one page at a time (for now, use page 2 if available)
    image_path = png_files[0]  # Use page 1
    
    # Determine page number from filename
    page_number = int(Path(image_path).stem.replace("page", ""))
    
    # Set up Gemini client (API key must be in GEMINI_API_KEY env var)
    client = genai.Client()
    gemini_file = upload_image_to_gemini(image_path, client)
    result = transcribe_atari_basic(gemini_file, client)
    
    # Save transcription to markdown file
    output_path = save_transcription_to_markdown(result, page_number)
    
    print(f"\nProcessed: {image_path}")
    print(f"Output saved to: {output_path}")
    print("\nGemini Transcription Result:\n")
    print(result)
    
    # Clean up uploaded file
    delete_gemini_file(gemini_file.name, client)

if __name__ == "__main__":
    main()
