"""
Atari BASIC Book Extraction Tool

This script automates the extraction of Atari BASIC program listings from scanned book pages. It downloads page images from the Atari Archives, converts them to PNG, and uses Google Gemini AI to identify and transcribe BASIC program listings into markdown files. The workflow includes:

1. Downloading and converting images for a specified page range.
2. Uploading images to Gemini and identifying all BASIC programs and their locations.
3. Extracting the source code for each program and saving it in markdown format.

Usage:
  python process.py [--start N] [--end M] [--output-dir DIR] [options]

Options allow for running only specific phases (download, conversion, program location extraction, or source extraction).

Requirements:
- GEMINI_API_KEY environment variable must be set
- Internet connection for image downloads and API calls
"""
#!/usr/bin/env python3
import time
import requests
from pathlib import Path
from PIL import Image
from google import genai
import os
import argparse
import json
import re
from typing import Any, Optional

# Module-level constants
ATARI_BASE_IMG_URL = "https://www.atariarchives.org/basicgames/pages/page"
DEFAULT_OUTPUT_DIR = "transcriptions"
DEFAULT_DOWNLOADS_DIR = "downloads"
DEFAULT_PNG_OUTPUT_DIR = "png_output"
GEMINI_MODEL_NAME = "gemini-2.5-flash"

# Helper function: check if a file exists at the given path
def file_exists(path: Path) -> bool:
    """Check if a file exists at the given path."""
    return path.exists()

# Helper function: print a summary of the download and conversion process
def print_download_summary(downloaded_files: list[Path], cached_count: int, download_count: int, download_errors: list, convert_errors: list) -> None:
    """Print a summary of the download and conversion process."""
    print(f"📊 Download summary: {len(downloaded_files)} successful, {cached_count} cached, {download_count} downloaded")
    if download_errors:
        print(f"❌ Download failures ({len(download_errors)}):")
        for url, error in download_errors:
            print(f"  - {url}: {error}")
    if convert_errors:
        print(f"❌ Conversion failures ({len(convert_errors)}):")
        for file_path, error in convert_errors:
            print(f"  - {file_path}: {error}")

# === Image Download and Conversion Utilities ===
def generate_atari_image_urls(start: int = 1, end: int = 185) -> list[str]:
    """Generate a list of Atari BASIC book page image URLs for the given page range."""
    if start < 1 or end < start:
        raise ValueError("Invalid page range. Start page must be 1 or greater, and end page must be at least start page.")
    return [f"{ATARI_BASE_IMG_URL}{page}.gif" for page in range(start, end + 1)]

def convert_to_png(src_path: Path, dest_dir: Optional[str] = "png_output", verbose: bool = False) -> Path:
    """Converts an image file to PNG format using Pillow, saving to dest_dir."""
    if not src_path.exists():
        raise FileNotFoundError(f"Source file not found: {src_path}")
    
    dest_dir = Path(dest_dir or DEFAULT_PNG_OUTPUT_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    png_path = dest_dir / (Path(src_path).stem + ".png")
    
    # Check if PNG already exists
    if png_path.exists():
        print(f"📁 Using cached PNG: {png_path}")
        return png_path
    
    try:
        if verbose:
            print(f"🔍 VERBOSE: Converting {src_path} to PNG format")
        
        img = Image.open(src_path)
        img.save(png_path, format="PNG", optimize=True)
        print(f"✅ Converted {src_path} -> {png_path}")
        
        if verbose:
            file_size = png_path.stat().st_size
            print(f"🔍 VERBOSE: PNG file size: {file_size:,} bytes")
        
        return png_path
    except Exception as e:
        print(f"❌ Failed to convert {src_path} to PNG: {e}")
        raise

def download_images(urls: list[str], save_dir: Optional[str] = "downloads", pause_seconds: float = 0.25, verbose: bool = False) -> list[Path]:
    """Download images from the given URLs, convert to PNG, and return list of PNG Paths."""
    if not urls:
        raise ValueError("No URLs provided for image download.")
    
    Path(save_dir or DEFAULT_DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    downloaded_files = []
    cached_count = 0
    download_count = 0
    convert_errors = []
    download_errors = []
    
    if verbose:
        print(f"🔍 VERBOSE: Starting download of {len(urls)} images to {save_dir}")
    
    for i, url in enumerate(urls, 1):
        filename = url.split("/")[-1]
        save_path = Path(save_dir) / filename
        
        if file_exists(save_path):
            print(f"📁 ({i}/{len(urls)}) Using cached file: {save_path}")
            cached_count += 1
        else:
            print(f"📥 ({i}/{len(urls)}) Downloading {url} -> {save_path}")
            try:
                response = requests.get(url)
                response.raise_for_status()
                with open(save_path, "wb") as f:
                    f.write(response.content)
                print(f"✅ Downloaded: {save_path}")
                download_count += 1
                time.sleep(pause_seconds)
            except Exception as e:
                error_msg = f"Failed to download {url}: {e}"
                print(f"❌ {error_msg}")
                download_errors.append((url, str(e)))
                continue
        
        try:
            png_path = convert_to_png(save_path, verbose=verbose)
            downloaded_files.append(png_path)
        except Exception as e:
            error_msg = f"Failed to convert {save_path}: {e}"
            print(f"❌ {error_msg}")
            convert_errors.append((str(save_path), str(e)))
    
    print_download_summary(downloaded_files, cached_count, download_count, download_errors, convert_errors)
    
    if verbose:
        print(f"🔍 VERBOSE: Final downloaded files count: {len(downloaded_files)}")
    
    return downloaded_files

# === Gemini API Upload Utilities ===
def upload_image_to_gemini(image_path: Path, client: Any) -> Any:
    """Upload a single image to Gemini and return the uploaded file object."""
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found for upload: {image_path}")
    
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

def upload_multiple_images_to_gemini(image_paths: list[Path], client: Any) -> list[Any]:
    """Upload multiple images to Gemini and return list of uploaded file objects."""
    if not image_paths:
        raise ValueError("No image paths provided for Gemini upload.")
    
    uploaded_files = []
    for image_path in image_paths:
        print(f"Uploading {image_path}...")
        file = upload_image_to_gemini(image_path, client)
        uploaded_files.append(file)
    return uploaded_files

# === Program Location and Source Extraction Utilities ===
def get_unique_pages_from_programs(programs: list[dict]) -> list[int]:
    """Extract all unique page numbers needed for all programs."""
    if not programs:
        return []
    unique_pages = set()
    for program in programs:
        pages = program.get('pages', [])
        unique_pages.update(pages)
    return sorted(list(unique_pages))

def get_png_paths_for_pages(page_numbers: list[int], verbose: bool = False) -> dict[int, Path]:
    """Map page numbers to their PNG file paths. Returns a dict of page number to Path."""
    if not page_numbers:
        return {}
    
    png_paths = {}
    missing_files = []
    
    if verbose:
        print(f"🔍 VERBOSE: Checking PNG files for {len(page_numbers)} pages: {page_numbers}")
    
    for page_num in page_numbers:
        png_path = Path(DEFAULT_PNG_OUTPUT_DIR) / f"page{page_num}.png"
        if png_path.exists():
            png_paths[page_num] = png_path
            if verbose:
                print(f"✅ VERBOSE: Found PNG for page {page_num}: {png_path}")
        else:
            missing_files.append(page_num)
            print(f"⚠️  PNG file not found for page {page_num}: {png_path}")
    
    if verbose:
        print(f"📊 VERBOSE: Found {len(png_paths)} PNG files, missing {len(missing_files)} files")
        if missing_files:
            print(f"❌ VERBOSE: Missing pages: {missing_files}")
    
    return png_paths

def upload_images_for_pages(page_numbers: list[int], client: Any, verbose: bool = False) -> dict[int, Any]:
    """Upload only the needed images and return a mapping from page number to Gemini file object."""
    if not page_numbers:
        raise ValueError("No page numbers provided for image upload.")
    
    png_paths = get_png_paths_for_pages(page_numbers, verbose=verbose)
    page_to_gemini_file = {}
    upload_errors = []
    
    requested_pages = len(page_numbers)
    available_pages = len(png_paths)
    missing_pages = requested_pages - available_pages
    
    print(f"📤 Uploading {available_pages} specific images (requested: {requested_pages}, missing: {missing_pages})")
    print(f"📊 Available pages: {', '.join(map(str, sorted(png_paths.keys())))}")
    
    if missing_pages > 0:
        missing_page_nums = [p for p in page_numbers if p not in png_paths]
        print(f"⚠️  Skipping {missing_pages} missing pages: {missing_page_nums}")
    
    for i, (page_num, png_path) in enumerate(png_paths.items(), 1):
        try:
            print(f"📤 ({i}/{len(png_paths)}) Uploading page {page_num}: {png_path}...")
            gemini_file = upload_image_to_gemini(png_path, client)
            page_to_gemini_file[page_num] = gemini_file
            if verbose:
                print(f"✅ VERBOSE: Successfully uploaded page {page_num} as {gemini_file.name}")
        except Exception as e:
            upload_errors.append((page_num, str(e)))
            print(f"❌ Failed to upload page {page_num}: {e}")
    
    success_count = len(page_to_gemini_file)
    print(f"✅ Upload complete: {success_count}/{available_pages} images uploaded successfully")
    
    if upload_errors:
        print(f"❌ Upload errors for {len(upload_errors)} pages:")
        for page_num, error in upload_errors:
            print(f"  - Page {page_num}: {error}")
    
    if verbose:
        print(f"🔍 VERBOSE: Final page-to-file mapping: {list(page_to_gemini_file.keys())}")
    
    return page_to_gemini_file

def create_page_to_file_mapping(gemini_files: list[Any], start_page: int, verbose: bool = False) -> dict[int, Any]:
    """Create a mapping from page numbers to gemini files for sequential uploads."""
    if not gemini_files:
        raise ValueError("No Gemini files provided for mapping.")
    
    if verbose:
        print(f"🔍 VERBOSE: Creating page-to-file mapping for {len(gemini_files)} files starting from page {start_page}")
    
    page_to_gemini_file = {}
    for i, gemini_file in enumerate(gemini_files):
        page_num = start_page + i
        page_to_gemini_file[page_num] = gemini_file
        if verbose:
            print(f"🔍 VERBOSE: Mapped page {page_num} -> {gemini_file.name}")
    
    if verbose:
        print(f"🔍 VERBOSE: Created mapping for pages: {sorted(page_to_gemini_file.keys())}")
    
    return page_to_gemini_file

def delete_gemini_file(file_name: str, client: Any) -> None:
    """Delete a file from Gemini by file name."""
    if not file_name:
        raise ValueError("File name is empty for deletion.")
    client.files.delete(name=file_name)
    print(f"Deleted Gemini file: {file_name}")

# === Program List and File I/O Utilities ===
def save_transcription_to_markdown(transcription: str, page_range: list[int], output_dir: Optional[str] = "transcriptions") -> Path:
    """Save transcription result to a markdown file and return the output Path."""
    output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
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

def identify_basic_programs(files: list[Any], client: Any, verbose: bool = False) -> str:
    """Scan all images to identify BASIC program listings and their names. Returns Gemini response text."""
    if not files:
        raise ValueError("No Gemini files provided for program location extraction.")
    
    prompt = (
        "PROGRAM LOCATION EXTRACTION\n\n"
        "Please scan through all the provided images of Atari BASIC book pages and identify every BASIC program listing. "
        "Look for program source code that appears in a terminal-like computer typeface with line numbers. "
        "Programs may span multiple pages.\n\n"
        "For each program you find, provide:\n"
        "1. Program name/title\n"
        "2. Page numbers where the program appears\n"
        "3. Brief description if available\n\n"
        "IMPORTANT: Look only for the actual BASIC source code listings (lines with numbers like 10, 20, 30, etc.) "
        "in computer terminal font. DO NOT include program execution output or sample runs.\n\n"
        "Return your findings in this exact JSON format:\n"
        "```json\n"
        "{\n"
        "  \"programs\": [\n"
        "    {\n"
        "      \"name\": \"Program Name\",\n"
        "      \"pages\": [1, 2, 3],\n"
        "      \"description\": \"Brief description\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )
    
    print(f"Program Location Extraction: Identifying BASIC programs across {len(files)} images...")
    contents = [prompt] + files
    
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=contents
    )
    
    if verbose:
        print("\n=== VERBOSE: Program Location Extraction Gemini Response ===")
        print(response.text)
        print("=== END VERBOSE ===\n")
    
    return response.text

def filter_files_by_pages(all_files: list[Any], page_numbers: list[int]) -> list[Any]:
    """Filter Gemini files to only include files for specific page numbers."""
    if not page_numbers:
        return all_files
    
    filtered_files = []
    for file in all_files:
        # Extract page number from file name (e.g., "files/abc123" -> need to map back to original)
        # We need to find the corresponding page number
        # The files are uploaded in order, so we can use the index
        file_index = all_files.index(file)
        page_number = file_index + 1  # Pages are 1-indexed
        
        if page_number in page_numbers:
            filtered_files.append(file)
    
    return filtered_files

def extract_program_source(files: list[Any], program_name: str, page_numbers: list[int], client: Any, verbose: bool = False) -> str:
    """Extract source code for a specific program from Gemini files. Returns Gemini response text."""
    if not files:
        raise ValueError("No Gemini files provided for program source extraction.")
    if not program_name:
        raise ValueError("Program name is empty for source extraction.")
    if not page_numbers:
        raise ValueError("Page numbers are empty for source extraction.")
    
    # Filter files to only include relevant pages
    filtered_files = filter_files_by_pages(files, page_numbers)
    
    pages_str = ", ".join(map(str, page_numbers)) if page_numbers else "all pages"
    prompt = (
        f"PROGRAM SOURCE EXTRACTION\n\n"
        f"Please extract the complete BASIC source code for the program '{program_name}' from the provided images "
        f"(expected on pages: {pages_str}). "
        f"Look for the source code listing that appears in terminal-like computer typeface with line numbers.\n\n"
        f"IMPORTANT GUIDELINES:\n"
        f"- Extract ONLY the BASIC source code (lines starting with numbers like 10, 20, 30, etc.)\n"
        f"- DO NOT include program execution output, sample runs, or example gameplay\n"
        f"- Maintain exact formatting, spacing, and line numbers as they appear\n"
        f"- If the program spans multiple pages, combine all source lines in order\n"
        f"- Include any comments or REM statements that are part of the source code\n\n"
        f"Return the source code in markdown format:\n"
        f"```basic\n"
        f"[SOURCE CODE HERE]\n"
        f"```"
    )
    
    print(f"Program Source Extraction: Extracting source code for '{program_name}' (pages: {pages_str}, {len(filtered_files)} images)...")
    contents = [prompt] + filtered_files
    
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=contents
    )
    
    if verbose:
        print(f"\n=== VERBOSE: Program Source Extraction Response for '{program_name}' ===")
        print(f"Pages: {pages_str}")
        print(f"Filtered files: {len(filtered_files)}/{len(files)}")
        print(response.text)
        print("=== END VERBOSE ===\n")
    
    return response.text

def extract_program_source_optimized(files_for_program: list[Any], program_name: str, page_numbers: list[int], client: Any, verbose: bool = False) -> str:
    """Extract source code using pre-filtered files (optimized version). Returns Gemini response text."""
    if not files_for_program:
        raise ValueError("No Gemini files provided for optimized source extraction.")
    if not program_name:
        raise ValueError("Program name is empty for optimized source extraction.")
    if not page_numbers:
        raise ValueError("Page numbers are empty for optimized source extraction.")
    
    pages_str = ", ".join(map(str, page_numbers)) if page_numbers else "all pages"
    prompt = (
        f"PROGRAM SOURCE EXTRACTION\n\n"
        f"Please extract the complete BASIC source code for the program '{program_name}' from the provided images "
        f"(expected on pages: {pages_str}). "
        f"Look for the source code listing that appears in terminal-like computer typeface with line numbers.\n\n"
        f"IMPORTANT GUIDELINES:\n"
        f"- Extract ONLY the BASIC source code (lines starting with numbers like 10, 20, 30, etc.)\n"
        f"- DO NOT include program execution output, sample runs, or example gameplay\n"
        f"- Maintain exact formatting, spacing, and line numbers as they appear\n"
        f"- If the program spans multiple pages, combine all source lines in order\n"
        f"- Include any comments or REM statements that are part of the source code\n\n"
        f"Return the source code in markdown format:\n"
        f"```basic\n"
        f"[SOURCE CODE HERE]\n"
        f"```"
    )
    
    print(f"Program Source Extraction: Extracting source code for '{program_name}' (pages: {pages_str}, {len(files_for_program)} images)...")
    contents = [prompt] + files_for_program
    
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=contents
    )
    
    if verbose:
        print(f"\n=== VERBOSE: Program Source Extraction Response for '{program_name}' ===")
        print(f"Pages: {pages_str}")
        print(f"Images provided: {len(files_for_program)}")
        print(response.text)
        print("=== END VERBOSE ===\n")
    
    return response.text

def parse_program_list(response_text: str, verbose: bool = False) -> list[dict]:
    """Parse the JSON response from program identification phase. Returns a list of program dicts."""
    if not response_text:
        print("❌ Error: Empty response from Gemini")
        return []
    
    if verbose:
        print(f"🔍 VERBOSE: Parsing program list from response ({len(response_text)} chars)")
    
    try:
        # Extract JSON from markdown code block if present
        json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
            if verbose:
                print(f"🔍 VERBOSE: Found JSON in markdown code block")
        else:
            json_text = response_text
            if verbose:
                print(f"🔍 VERBOSE: Using entire response as JSON")
        
        data = json.loads(json_text)
        programs = data.get('programs', [])
        
        if verbose:
            print(f"🔍 VERBOSE: Successfully parsed {len(programs)} programs from JSON")
            if programs:
                total_pages = set()
                for program in programs:
                    total_pages.update(program.get('pages', []))
                print(f"🔍 VERBOSE: Programs span {len(total_pages)} unique pages: {sorted(total_pages)}")
        
        return programs
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON response: {e}")
        if verbose:
            print(f"🔍 VERBOSE: Failed JSON text (first 500 chars): {json_text[:500]}...")
        print(f"Raw response text (first 200 chars): {response_text[:200]}...")
        return []

def save_program_list_to_json(programs: list[dict], output_dir: Optional[str] = "transcriptions") -> Path:
    """Save program list to JSON file for debugging/reuse. Returns the output Path."""
    output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = output_dir / "program_list.json"
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"programs": programs}, f, indent=2)
    
    print(f"Saved program list to: {json_path}")
    return json_path

def load_program_list_from_json(json_path: str, verbose: bool = False) -> list[dict]:
    """Load program list from JSON file. Returns a list of program dicts."""
    if verbose:
        print(f"🔍 VERBOSE: Loading program list from {json_path}")
    
    try:
        if not Path(json_path).exists():
            print(f"❌ Program list file not found: {json_path}")
            return []
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        programs = data.get("programs", [])
        if verbose:
            print(f"✅ VERBOSE: Loaded {len(programs)} programs from JSON")
            for i, program in enumerate(programs[:5], 1):  # Show first 5 for verbose
                pages = program.get('pages', [])
                print(f"  {i}. {program.get('name', 'Unknown')} (pages: {pages})")
            if len(programs) > 5:
                print(f"  ... and {len(programs) - 5} more programs")
        
        return programs
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading program list from {json_path}: {e}")
        return []

def save_program_to_file(program_name: str, source_code: str, output_dir: Optional[str] = "programs") -> Path:
    """Save individual program source code to a markdown file. Returns the output Path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create safe filename from program name
    safe_name = re.sub(r'[^\w\s-]', '', program_name).strip()
    safe_name = re.sub(r'[-\s]+', '-', safe_name)
    filename = f"{safe_name.lower()}.md"
    output_path = output_dir / filename
    
    # Create markdown content
    markdown_content = f"# {program_name}\n\n{source_code}\n"
    
    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    print(f"Saved program '{program_name}' to: {output_path}")
    return output_path

# === Command-Line Argument Parsing ===
def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments and return the parsed Namespace."""
    parser = argparse.ArgumentParser(
        description="Atari Basic Book Scan Tools - Extract BASIC programs from scanned book pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process.py                    # Process pages 1-10 (default)
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
        "--output-dir", 
        default="transcriptions", 
        help="Output directory for markdown files (default: transcriptions)"
    )
    
    parser.add_argument(
        "--download-pause",
        type=float,
        default=0.25,
        help="Pause between downloads in seconds (default: 0.25)"
    )
    
    # Debug and phase-specific options
    parser.add_argument(
        "--download-images-only",
        action="store_true",
        help="Only download and convert images, then exit"
    )
    
    parser.add_argument(
        "--convert-images-only",
        action="store_true",
        help="Only convert existing GIF files to PNG, then exit"
    )
    
    parser.add_argument(
        "--locate-programs-only",
        action="store_true",
        help="Only run program location extraction and save results to JSON"
    )
    
    parser.add_argument(
        "--extract-source-only",
        action="store_true",
        help="Only run program source extraction using existing program list JSON"
    )
    
    parser.add_argument(
        "--program-list",
        help="Path to JSON file containing program list (for --extract-source-only)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output including full Gemini responses"
    )
    
    return parser.parse_args()

# === Main Workflow and Orchestration ===
def handle_download_images_only(start_page: int, end_page: int, download_pause: float, verbose: bool) -> None:
    """Handle the download-images-only mode: download and convert images, then exit."""
    print(f"\n📥 Download-images-only mode: Downloading {end_page - start_page + 1} images...")
    urls = generate_atari_image_urls(start=start_page, end=end_page)
    png_files = download_images(urls, pause_seconds=download_pause, verbose=verbose)
    print(f"✅ Downloaded and converted {len(png_files)} images")

def handle_convert_images_only(start_page: int, end_page: int, verbose: bool) -> None:
    """Handle the convert-images-only mode: convert existing GIF files to PNG, then exit."""
    print(f"\n🔄 Convert-images-only mode: Converting existing GIF files to PNG...")
    png_files = []
    for page in range(start_page, end_page + 1):
        gif_path = Path(DEFAULT_DOWNLOADS_DIR) / f"page{page}.gif"
        if gif_path.exists():
            try:
                png_path = convert_to_png(gif_path, verbose=verbose)
                png_files.append(png_path)
            except Exception as e:
                print(f"❌ Failed to convert {gif_path}: {e}")
    print(f"✅ Converted {len(png_files)} images")

def handle_locate_programs_only(gemini_files: list[Any], output_dir: str, verbose: bool) -> None:
    """Handle the locate-programs-only mode: identify BASIC programs and save results to JSON."""
    print(f"\n🔍 Program Location Extraction: Identifying BASIC programs...")
    program_list_response = identify_basic_programs(gemini_files, client, verbose=verbose)
    programs = parse_program_list(program_list_response, verbose=verbose)
    if not programs:
        print("❌ No programs found in the images.")
        return
    print(f"✅ Found {len(programs)} programs:")
    for i, program in enumerate(programs, 1):
        pages_str = ", ".join(map(str, program.get('pages', [])))
        print(f"  {i}. {program['name']} (pages: {pages_str})")
    save_program_list_to_json(programs, output_dir)

def handle_extract_source_only(program_list_path: str, output_dir: str, verbose: bool) -> None:
    """Handle the extract-source-only mode: extract program source using existing program list JSON."""
    print(f"\n📝 Program Source Extraction: Loading program list from {program_list_path}")
    programs = load_program_list_from_json(program_list_path, verbose=verbose)
    if not programs:
        print("❌ No programs found in the program list file.")
        return
    print(f"✅ Loaded {len(programs)} programs from file")
    unique_pages = get_unique_pages_from_programs(programs)
    print(f"📊 Programs need {len(unique_pages)} unique pages: {', '.join(map(str, unique_pages))}")
    page_to_gemini_file = upload_images_for_pages(unique_pages, client, verbose=verbose)
    if not page_to_gemini_file:
        print("❌ No images could be uploaded.")
        return
    try:
        saved_files = []
        skipped_programs = []
        failed_programs = []
        for i, program in enumerate(programs, 1):
            program_name = program['name']
            page_numbers = program.get('pages', [])
            pages_str = ', '.join(map(str, page_numbers))
            print(f"\n📋 ({i}/{len(programs)}) Processing '{program_name}' (pages: {pages_str})...")
            if verbose:
                print(f"🔍 VERBOSE: Program '{program_name}' expects {len(page_numbers)} pages: {page_numbers}")
            try:
                files_for_program = []
                missing_pages = []
                for page in page_numbers:
                    if page in page_to_gemini_file:
                        files_for_program.append(page_to_gemini_file[page])
                    else:
                        missing_pages.append(page)
                if verbose:
                    print(f"🔍 VERBOSE: Found files for {len(files_for_program)}/{len(page_numbers)} pages")
                    if missing_pages:
                        print(f"🔍 VERBOSE: Missing pages for '{program_name}': {missing_pages}")
                if not files_for_program:
                    skip_msg = f"No files found for '{program_name}' on pages {page_numbers}"
                    print(f"⚠️  {skip_msg}")
                    skipped_programs.append((program_name, skip_msg))
                    continue
                if missing_pages:
                    print(f"⚠️  Partial data: missing {len(missing_pages)} pages for '{program_name}': {missing_pages}")
                print(f"🤖 Calling Gemini AI to extract source code...")
                source_code = extract_program_source_optimized(files_for_program, program_name, page_numbers, client, verbose=verbose)
                if not source_code.strip():
                    skip_msg = f"Empty response from Gemini for '{program_name}'"
                    print(f"⚠️  {skip_msg}")
                    skipped_programs.append((program_name, skip_msg))
                    continue
                output_path = save_program_to_file(program_name, source_code, output_dir)
                saved_files.append(output_path)
                print(f"✅ Successfully saved '{program_name}' -> {output_path}")
            except Exception as e:
                error_msg = f"Error processing '{program_name}': {e}"
                print(f"❌ {error_msg}")
                failed_programs.append((program_name, str(e)))
                if verbose:
                    import traceback
                    print(f"🔍 VERBOSE: Full traceback for '{program_name}':")
                    traceback.print_exc()
        print(f"\n🎉 Program Source Extraction complete!")
        print(f"📊 Summary:")
        print(f"  - Total programs in list: {len(programs)}")
        print(f"  - Successfully saved: {len(saved_files)}")
        print(f"  - Skipped (no data): {len(skipped_programs)}")
        print(f"  - Failed (errors): {len(failed_programs)}")
        if saved_files:
            print(f"\n✅ Successfully saved programs:")
            for i, file_path in enumerate(saved_files, 1):
                print(f"  {i}. {file_path}")
        if skipped_programs:
            print(f"\n⚠️  Skipped programs ({len(skipped_programs)}):")
            for program_name, reason in skipped_programs:
                print(f"  - {program_name}: {reason}")
        if failed_programs:
            print(f"\n❌ Failed programs ({len(failed_programs)}):")
            for program_name, error in failed_programs:
                print(f"  - {program_name}: {error}")
    finally:
        print(f"\n🧹 Cleaning up uploaded files...")
        for gemini_file in page_to_gemini_file.values():
            delete_gemini_file(gemini_file.name, client)
        print("✅ Cleanup complete")

def handle_default_workflow(start_page: int, end_page: int, download_pause: float, output_dir: str, verbose: bool) -> None:
    """Handle the default workflow: download, convert, upload, locate programs, and extract sources."""
    print(f"\n📥 Downloading and converting {end_page - start_page + 1} images...")
    urls = generate_atari_image_urls(start=start_page, end=end_page)
    png_files = download_images(urls, pause_seconds=download_pause, verbose=verbose)
    if not png_files:
        print("❌ No images downloaded.")
        return
    print(f"✅ Successfully processed {len(png_files)} images")
    print(f"\n📤 Uploading {len(png_files)} images to Gemini...")
    gemini_files = upload_multiple_images_to_gemini(png_files, client)
    print(f"✅ All images uploaded successfully")
    try:
        handle_locate_programs_only(gemini_files, output_dir, verbose)
        # After locating programs, extract sources
        # Reload program list from output_dir
        programs = load_program_list_from_json(Path(output_dir) / "program_list.json", verbose=verbose)
        if not programs:
            print("❌ No programs found in the program list file.")
            return
        unique_pages = get_unique_pages_from_programs(programs)
        page_to_gemini_file = create_page_to_file_mapping(gemini_files, start_page, verbose=verbose)
        saved_files = []
        skipped_programs = []
        failed_programs = []
        for i, program in enumerate(programs, 1):
            program_name = program['name']
            page_numbers = program.get('pages', [])
            pages_str = ', '.join(map(str, page_numbers))
            print(f"\n📋 ({i}/{len(programs)}) Processing '{program_name}' (pages: {pages_str})...")
            if verbose:
                print(f"🔍 VERBOSE: Program '{program_name}' expects {len(page_numbers)} pages: {page_numbers}")
            try:
                files_for_program = []
                missing_pages_for_program = []
                for page in page_numbers:
                    if page in page_to_gemini_file:
                        files_for_program.append(page_to_gemini_file[page])
                    else:
                        missing_pages_for_program.append(page)
                if verbose:
                    print(f"🔍 VERBOSE: Found files for {len(files_for_program)}/{len(page_numbers)} pages")
                    if missing_pages_for_program:
                        print(f"🔍 VERBOSE: Missing pages for '{program_name}': {missing_pages_for_program}")
                if not files_for_program:
                    skip_msg = f"No files found for '{program_name}' on pages {page_numbers}"
                    print(f"⚠️  {skip_msg}")
                    skipped_programs.append((program_name, skip_msg))
                    continue
                if missing_pages_for_program:
                    print(f"⚠️  Partial data: missing {len(missing_pages_for_program)} pages for '{program_name}': {missing_pages_for_program}")
                print(f"🤖 Calling Gemini AI to extract source code...")
                source_code = extract_program_source_optimized(files_for_program, program_name, page_numbers, client, verbose=verbose)
                if not source_code.strip():
                    skip_msg = f"Empty response from Gemini for '{program_name}'"
                    print(f"⚠️  {skip_msg}")
                    skipped_programs.append((program_name, skip_msg))
                    continue
                output_path = save_program_to_file(program_name, source_code, output_dir)
                saved_files.append(output_path)
                print(f"✅ Successfully saved '{program_name}' -> {output_path}")
            except Exception as e:
                error_msg = f"Error processing '{program_name}': {e}"
                print(f"❌ {error_msg}")
                failed_programs.append((program_name, str(e)))
                if verbose:
                    import traceback
                    print(f"🔍 VERBOSE: Full traceback for '{program_name}':")
                    traceback.print_exc()
        print(f"\n🎉 Processing complete!")
        print(f"📊 Summary:")
        print(f"  - Images processed: {len(png_files)}")
        print(f"  - Programs found: {len(programs)}")
        print(f"  - Successfully saved: {len(saved_files)}")
        print(f"  - Skipped (no data): {len(skipped_programs)}")
        print(f"  - Failed (errors): {len(failed_programs)}")
        print(f"  - Output directory: {output_dir}")
        if saved_files:
            print(f"\n✅ Successfully saved programs:")
            for i, file_path in enumerate(saved_files, 1):
                print(f"  {i}. {file_path}")
        if skipped_programs:
            print(f"\n⚠️  Skipped programs ({len(skipped_programs)}):")
            for program_name, reason in skipped_programs:
                print(f"  - {program_name}: {reason}")
        if failed_programs:
            print(f"\n❌ Failed programs ({len(failed_programs)}):")
            for program_name, error in failed_programs:
                print(f"  - {program_name}: {error}")
    finally:
        print(f"\n🧹 Cleaning up uploaded files...")
        for gemini_file in gemini_files:
            delete_gemini_file(gemini_file.name, client)
        print("✅ Cleanup complete")

def main() -> None:
    """Main entry point for the script. Handles argument parsing and workflow orchestration."""
    args = parse_arguments()
    start_page = args.start
    end_page = args.end
    global client
    client = genai.Client()
    if args.download_images_only:
        handle_download_images_only(start_page, end_page, args.download_pause, args.verbose)
        return
    if args.convert_images_only:
        handle_convert_images_only(start_page, end_page, args.verbose)
        return
    if args.extract_source_only:
        if not args.program_list:
            print("❌ --program-list is required for --extract-source-only mode")
            return
        handle_extract_source_only(args.program_list, args.output_dir, args.verbose)
        return
    handle_default_workflow(start_page, end_page, args.download_pause, args.output_dir, args.verbose)

if __name__ == "__main__":
    main()
