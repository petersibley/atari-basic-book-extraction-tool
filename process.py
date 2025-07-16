#!/usr/bin/env python3
import time
import requests
from pathlib import Path
from PIL import Image
from google import genai
import os
import argparse

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

def upload_multiple_images_to_gemini(image_paths, client):
    """Upload multiple images to Gemini and return list of uploaded files."""
    uploaded_files = []
    for image_path in image_paths:
        print(f"Uploading {image_path}...")
        file = upload_image_to_gemini(image_path, client)
        uploaded_files.append(file)
    return uploaded_files

def delete_gemini_file(file_name, client):
    client.files.delete(name=file_name)
    print(f"Deleted Gemini file: {file_name}")

def save_transcription_to_markdown(transcription, page_range, output_dir="transcriptions"):
    """Save transcription result to a markdown file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename based on page range
    if len(page_range) == 1:
        filename = f"page_{page_range[0]:02d}.md"
    else:
        filename = f"pages_{page_range[0]:02d}-{page_range[-1]:02d}.md"
    output_path = output_dir / filename
    
    # Write transcription to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(transcription)
    
    print(f"Saved transcription to: {output_path}")
    return output_path

def transcribe_atari_basic(files, client):
    prompt = (
        "Please extract and transcribe all text content from these images of Atari BASIC book pages. "
        "Pay special attention to any BASIC program listings. The images may contain Atari BASIC code "
        "with line numbers in a terminal-like computer typeface. If you find any BASIC programs, "
        "please transcribe them exactly as they appear, maintaining the original formatting and line numbers. "
        "If there are program titles or names, please note them as well. "
        "For each program found, create a separate markdown section with the program title as a heading. "
        "Provide all transcribed content in markdown format."
    )
    
    # Create contents list with prompt and all files
    contents = [prompt] + files
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents
    )
    return response.text

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Atari Basic Book Scan Tools - Extract BASIC programs from scanned book pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process.py                    # Process pages 1-10 (default)
  python process.py --page 5          # Process only page 5
  python process.py --start 1 --end 5 # Process pages 1-5
  python process.py --output-dir docs # Save to docs/ directory

This script downloads GIF images from Atari Archives, converts them to PNG,
and uses Google Gemini AI to transcribe BASIC programs into markdown files.

Requirements:
  - GEMINI_API_KEY environment variable must be set
  - Internet connection for downloading images and API calls
        """
    )
    
    parser.add_argument(
        "--start", 
        type=int, 
        default=1, 
        help="Start page number (default: 1)"
    )
    
    parser.add_argument(
        "--end", 
        type=int, 
        default=10, 
        help="End page number (default: 10)"
    )
    
    parser.add_argument(
        "--page", 
        type=int, 
        help="Process a specific page only (overrides --start and --end)"
    )
    
    parser.add_argument(
        "--output-dir", 
        default="transcriptions", 
        help="Output directory for markdown files (default: transcriptions)"
    )
    
    parser.add_argument(
        "--pause", 
        type=float, 
        default=0.5, 
        help="Pause between downloads in seconds (default: 0.5)"
    )
    
    return parser.parse_args()

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # Determine page range
    if args.page:
        start_page = args.page
        end_page = args.page
        print(f"Processing page {args.page}")
    else:
        start_page = args.start
        end_page = args.end
        print(f"Processing pages {start_page} to {end_page}")
    
    # Download and convert images
    urls = generate_atari_image_urls(start=start_page, end=end_page)
    png_files = download_images(urls, pause_seconds=args.pause)
    if not png_files:
        print("No images downloaded.")
        return
    
    # Process all available pages
    print(f"\nProcessing {len(png_files)} images...")
    
    # Extract page numbers for filename
    page_numbers = []
    for png_file in png_files:
        page_number = int(Path(png_file).stem.replace("page", ""))
        page_numbers.append(page_number)
    
    # Set up Gemini client (API key must be in GEMINI_API_KEY env var)
    client = genai.Client()
    
    # Upload all images to Gemini
    gemini_files = upload_multiple_images_to_gemini(png_files, client)
    
    # Transcribe all images in one request
    result = transcribe_atari_basic(gemini_files, client)
    
    # Save transcription to markdown file
    output_path = save_transcription_to_markdown(result, page_numbers, args.output_dir)
    
    print(f"\nProcessed: {len(png_files)} images")
    print(f"Output saved to: {output_path}")
    print("\nGemini Transcription Result:\n")
    print(result)
    
    # Clean up uploaded files
    for gemini_file in gemini_files:
        delete_gemini_file(gemini_file.name, client)

if __name__ == "__main__":
    main()
