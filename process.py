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

def generate_atari_image_urls(start=1, end=185):
    base_img_url = "https://www.atariarchives.org/basicgames/pages/page"
    return [f"{base_img_url}{page}.gif" for page in range(start, end + 1)]

def convert_to_png(src_path, dest_dir="png_output", debug=False):
    """Converts an image file to PNG format using Pillow, saving to dest_dir."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    png_path = dest_dir / (Path(src_path).stem + ".png")
    
    # Check if PNG already exists
    if png_path.exists():
        print(f"📁 Using cached PNG: {png_path}")
        return png_path
    
    try:
        if debug:
            print(f"🔍 DEBUG: Converting {src_path} to PNG format")
        
        img = Image.open(src_path)
        img.save(png_path, format="PNG", optimize=True)
        print(f"✅ Converted {src_path} -> {png_path}")
        
        if debug:
            file_size = png_path.stat().st_size
            print(f"🔍 DEBUG: PNG file size: {file_size:,} bytes")
        
        return png_path
    except Exception as e:
        print(f"❌ Failed to convert {src_path} to PNG: {e}")
        raise

def download_images(urls, save_dir="downloads", pause_seconds=0.25, debug=False):
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    downloaded_files = []
    cached_count = 0
    download_count = 0
    convert_errors = []
    download_errors = []
    
    if debug:
        print(f"🔍 DEBUG: Starting download of {len(urls)} images to {save_dir}")
    
    for i, url in enumerate(urls, 1):
        filename = url.split("/")[-1]
        save_path = Path(save_dir) / filename
        
        # Check if file already exists
        if save_path.exists():
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
                # Only pause after actual downloads to avoid hammering the server
                time.sleep(pause_seconds)
            except Exception as e:
                error_msg = f"Failed to download {url}: {e}"
                print(f"❌ {error_msg}")
                download_errors.append((url, str(e)))
                continue
        
        try:
            png_path = convert_to_png(save_path, debug=debug)
            downloaded_files.append(png_path)
        except Exception as e:
            error_msg = f"Failed to convert {save_path}: {e}"
            print(f"❌ {error_msg}")
            convert_errors.append((str(save_path), str(e)))
    
    # Summary
    print(f"📊 Download summary: {len(downloaded_files)} successful, {cached_count} cached, {download_count} downloaded")
    
    if download_errors:
        print(f"❌ Download failures ({len(download_errors)}):")
        for url, error in download_errors:
            print(f"  - {url}: {error}")
    
    if convert_errors:
        print(f"❌ Conversion failures ({len(convert_errors)}):")
        for file_path, error in convert_errors:
            print(f"  - {file_path}: {error}")
    
    if debug:
        print(f"🔍 DEBUG: Final downloaded files count: {len(downloaded_files)}")
    
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

def get_unique_pages_from_programs(programs):
    """Extract all unique page numbers needed for all programs."""
    unique_pages = set()
    for program in programs:
        pages = program.get('pages', [])
        unique_pages.update(pages)
    return sorted(list(unique_pages))

def get_png_paths_for_pages(page_numbers, debug=False):
    """Map page numbers to their PNG file paths."""
    png_paths = {}
    missing_files = []
    
    if debug:
        print(f"🔍 DEBUG: Checking PNG files for {len(page_numbers)} pages: {page_numbers}")
    
    for page_num in page_numbers:
        png_path = Path("png_output") / f"page{page_num}.png"
        if png_path.exists():
            png_paths[page_num] = png_path
            if debug:
                print(f"✅ DEBUG: Found PNG for page {page_num}: {png_path}")
        else:
            missing_files.append(page_num)
            print(f"⚠️  PNG file not found for page {page_num}: {png_path}")
    
    if debug:
        print(f"📊 DEBUG: Found {len(png_paths)} PNG files, missing {len(missing_files)} files")
        if missing_files:
            print(f"❌ DEBUG: Missing pages: {missing_files}")
    
    return png_paths

def upload_images_for_pages(page_numbers, client, debug=False):
    """Upload only the needed images and return page-to-handle mapping."""
    png_paths = get_png_paths_for_pages(page_numbers, debug=debug)
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
            if debug:
                print(f"✅ DEBUG: Successfully uploaded page {page_num} as {gemini_file.name}")
        except Exception as e:
            upload_errors.append((page_num, str(e)))
            print(f"❌ Failed to upload page {page_num}: {e}")
    
    success_count = len(page_to_gemini_file)
    print(f"✅ Upload complete: {success_count}/{available_pages} images uploaded successfully")
    
    if upload_errors:
        print(f"❌ Upload errors for {len(upload_errors)} pages:")
        for page_num, error in upload_errors:
            print(f"  - Page {page_num}: {error}")
    
    if debug:
        print(f"🔍 DEBUG: Final page-to-file mapping: {list(page_to_gemini_file.keys())}")
    
    return page_to_gemini_file

def create_page_to_file_mapping(gemini_files, start_page, debug=False):
    """Create a mapping from page numbers to gemini files for sequential uploads."""
    page_to_gemini_file = {}
    
    if debug:
        print(f"🔍 DEBUG: Creating page-to-file mapping for {len(gemini_files)} files starting from page {start_page}")
    
    for i, gemini_file in enumerate(gemini_files):
        page_num = start_page + i
        page_to_gemini_file[page_num] = gemini_file
        if debug:
            print(f"🔍 DEBUG: Mapped page {page_num} -> {gemini_file.name}")
    
    if debug:
        print(f"🔍 DEBUG: Created mapping for pages: {sorted(page_to_gemini_file.keys())}")
    
    return page_to_gemini_file

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

def identify_basic_programs(files, client, debug=False):
    """Program Location Extraction: Scan all images to identify BASIC program listings and their names."""
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
        model="gemini-2.5-flash",
        contents=contents
    )
    
    if debug:
        print("\n=== DEBUG: Program Location Extraction Gemini Response ===")
        print(response.text)
        print("=== END DEBUG ===\n")
    
    return response.text

def filter_files_by_pages(all_files, page_numbers):
    """Filter gemini_files to only include files for specific page numbers."""
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

def extract_program_source(files, program_name, page_numbers, client, debug=False):
    """Program Source Extraction: Extract source code for a specific program."""
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
        model="gemini-2.5-flash",
        contents=contents
    )
    
    if debug:
        print(f"\n=== DEBUG: Program Source Extraction Response for '{program_name}' ===")
        print(f"Pages: {pages_str}")
        print(f"Filtered files: {len(filtered_files)}/{len(files)}")
        print(response.text)
        print("=== END DEBUG ===\n")
    
    return response.text

def extract_program_source_optimized(files_for_program, program_name, page_numbers, client, debug=False):
    """Program Source Extraction: Extract source code using pre-filtered files (optimized version)."""
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
        model="gemini-2.5-flash",
        contents=contents
    )
    
    if debug:
        print(f"\n=== DEBUG: Program Source Extraction Response for '{program_name}' ===")
        print(f"Pages: {pages_str}")
        print(f"Images provided: {len(files_for_program)}")
        print(response.text)
        print("=== END DEBUG ===\n")
    
    return response.text

def parse_program_list(response_text, debug=False):
    """Parse the JSON response from program identification phase."""
    if not response_text:
        print("❌ Error: Empty response from Gemini")
        return []
    
    if debug:
        print(f"🔍 DEBUG: Parsing program list from response ({len(response_text)} chars)")
    
    try:
        # Extract JSON from markdown code block if present
        json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
            if debug:
                print(f"🔍 DEBUG: Found JSON in markdown code block")
        else:
            json_text = response_text
            if debug:
                print(f"🔍 DEBUG: Using entire response as JSON")
        
        data = json.loads(json_text)
        programs = data.get('programs', [])
        
        if debug:
            print(f"🔍 DEBUG: Successfully parsed {len(programs)} programs from JSON")
            if programs:
                total_pages = set()
                for program in programs:
                    total_pages.update(program.get('pages', []))
                print(f"🔍 DEBUG: Programs span {len(total_pages)} unique pages: {sorted(total_pages)}")
        
        return programs
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON response: {e}")
        if debug:
            print(f"🔍 DEBUG: Failed JSON text (first 500 chars): {json_text[:500]}...")
        print(f"Raw response text (first 200 chars): {response_text[:200]}...")
        return []

def save_program_list_to_json(programs, output_dir="transcriptions"):
    """Save program list to JSON file for debugging/reuse."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = output_dir / "program_list.json"
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"programs": programs}, f, indent=2)
    
    print(f"Saved program list to: {json_path}")
    return json_path

def load_program_list_from_json(json_path, debug=False):
    """Load program list from JSON file."""
    if debug:
        print(f"🔍 DEBUG: Loading program list from {json_path}")
    
    try:
        if not Path(json_path).exists():
            print(f"❌ Program list file not found: {json_path}")
            return []
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        programs = data.get("programs", [])
        if debug:
            print(f"✅ DEBUG: Loaded {len(programs)} programs from JSON")
            for i, program in enumerate(programs[:5], 1):  # Show first 5 for debugging
                pages = program.get('pages', [])
                print(f"  {i}. {program.get('name', 'Unknown')} (pages: {pages})")
            if len(programs) > 5:
                print(f"  ... and {len(programs) - 5} more programs")
        
        return programs
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading program list from {json_path}: {e}")
        return []

def save_program_to_file(program_name, source_code, output_dir="programs"):
    """Save individual program source code to a markdown file."""
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
        default=0.25, 
        help="Pause between downloads in seconds (default: 0.25)"
    )
    
    # Debug and phase-specific options
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only download and convert images, then exit"
    )
    
    parser.add_argument(
        "--convert-only",
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
        "--debug",
        action="store_true",
        help="Enable debug output including full Gemini responses"
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
    
    # Handle download-only mode
    if args.download_only:
        print(f"\n📥 Download-only mode: Downloading {end_page - start_page + 1} images...")
        urls = generate_atari_image_urls(start=start_page, end=end_page)
        png_files = download_images(urls, pause_seconds=args.pause, debug=args.debug)
        print(f"✅ Downloaded and converted {len(png_files)} images")
        return
    
    # Handle convert-only mode
    if args.convert_only:
        print(f"\n🔄 Convert-only mode: Converting existing GIF files to PNG...")
        png_files = []
        for page in range(start_page, end_page + 1):
            gif_path = Path("downloads") / f"page{page}.gif"
            if gif_path.exists():
                try:
                    png_path = convert_to_png(gif_path, debug=args.debug)
                    png_files.append(png_path)
                except Exception as e:
                    print(f"❌ Failed to convert {gif_path}: {e}")
        print(f"✅ Converted {len(png_files)} images")
        return
    
    # Set up Gemini client (API key must be in GEMINI_API_KEY env var)
    client = genai.Client()
    
    # Handle extract-source-only mode differently (no bulk upload needed)
    if args.extract_source_only:
        # Extract-source-only mode handles its own image upload optimization
        pass
    else:
        # Download and convert images (for all other modes)
        print(f"\n📥 Downloading and converting {end_page - start_page + 1} images...")
        urls = generate_atari_image_urls(start=start_page, end=end_page)
        png_files = download_images(urls, pause_seconds=args.pause, debug=args.debug)
        if not png_files:
            print("❌ No images downloaded.")
            return
        
        print(f"✅ Successfully processed {len(png_files)} images")
        
        # Upload all images to Gemini
        print(f"\n📤 Uploading {len(png_files)} images to Gemini...")
        gemini_files = upload_multiple_images_to_gemini(png_files, client)
        print(f"✅ All images uploaded successfully")
    
    try:
        # Handle locate-programs-only mode
        if args.locate_programs_only:
            print(f"\n🔍 Program Location Extraction: Identifying BASIC programs...")
            program_list_response = identify_basic_programs(gemini_files, client, debug=args.debug)
            programs = parse_program_list(program_list_response, debug=args.debug)
            
            if not programs:
                print("❌ No programs found in the images.")
                return
            
            print(f"✅ Found {len(programs)} programs:")
            for i, program in enumerate(programs, 1):
                pages_str = ", ".join(map(str, program.get('pages', [])))
                print(f"  {i}. {program['name']} (pages: {pages_str})")
            
            # Save program list to JSON
            save_program_list_to_json(programs, args.output_dir)
            return
        
        # Handle extract-source-only mode (OPTIMIZED)
        if args.extract_source_only:
            if not args.program_list:
                print("❌ --program-list is required for --extract-source-only mode")
                return
            
            print(f"\n📝 Program Source Extraction: Loading program list from {args.program_list}")
            programs = load_program_list_from_json(args.program_list, debug=args.debug)
            
            if not programs:
                print("❌ No programs found in the program list file.")
                return
            
            print(f"✅ Loaded {len(programs)} programs from file")
            
            # OPTIMIZATION: Get unique pages and upload only those
            unique_pages = get_unique_pages_from_programs(programs)
            print(f"📊 Programs need {len(unique_pages)} unique pages: {', '.join(map(str, unique_pages))}")
            
            # Upload only the needed images
            page_to_gemini_file = upload_images_for_pages(unique_pages, client, debug=args.debug)
            
            if not page_to_gemini_file:
                print("❌ No images could be uploaded.")
                return
            
            try:
                # Extract source code for each program using optimized approach
                saved_files = []
                skipped_programs = []
                failed_programs = []
                
                for i, program in enumerate(programs, 1):
                    program_name = program['name']
                    page_numbers = program.get('pages', [])
                    pages_str = ', '.join(map(str, page_numbers))
                    
                    print(f"\n📋 ({i}/{len(programs)}) Processing '{program_name}' (pages: {pages_str})...")
                    
                    if args.debug:
                        print(f"🔍 DEBUG: Program '{program_name}' expects {len(page_numbers)} pages: {page_numbers}")
                    
                    try:
                        # Get the specific Gemini files for this program
                        files_for_program = []
                        missing_pages = []
                        
                        for page in page_numbers:
                            if page in page_to_gemini_file:
                                files_for_program.append(page_to_gemini_file[page])
                            else:
                                missing_pages.append(page)
                        
                        if args.debug:
                            print(f"🔍 DEBUG: Found files for {len(files_for_program)}/{len(page_numbers)} pages")
                            if missing_pages:
                                print(f"🔍 DEBUG: Missing pages for '{program_name}': {missing_pages}")
                        
                        if not files_for_program:
                            skip_msg = f"No files found for '{program_name}' on pages {page_numbers}"
                            print(f"⚠️  {skip_msg}")
                            skipped_programs.append((program_name, skip_msg))
                            continue
                        
                        if missing_pages:
                            print(f"⚠️  Partial data: missing {len(missing_pages)} pages for '{program_name}': {missing_pages}")
                        
                        print(f"🤖 Calling Gemini AI to extract source code...")
                        source_code = extract_program_source_optimized(files_for_program, program_name, page_numbers, client, debug=args.debug)
                        
                        if not source_code.strip():
                            skip_msg = f"Empty response from Gemini for '{program_name}'"
                            print(f"⚠️  {skip_msg}")
                            skipped_programs.append((program_name, skip_msg))
                            continue
                        
                        output_path = save_program_to_file(program_name, source_code, args.output_dir)
                        saved_files.append(output_path)
                        print(f"✅ Successfully saved '{program_name}' -> {output_path}")
                        
                    except Exception as e:
                        error_msg = f"Error processing '{program_name}': {e}"
                        print(f"❌ {error_msg}")
                        failed_programs.append((program_name, str(e)))
                        if args.debug:
                            import traceback
                            print(f"🔍 DEBUG: Full traceback for '{program_name}':")
                            traceback.print_exc()
                
                # Final summary for Program Source Extraction
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
                # Clean up uploaded files
                print(f"\n🧹 Cleaning up uploaded files...")
                for gemini_file in page_to_gemini_file.values():
                    delete_gemini_file(gemini_file.name, client)
                print("✅ Cleanup complete")
            
            return
        
        # Default: Run both phases with optimization
        # PROGRAM LOCATION EXTRACTION: Identify all BASIC programs
        print(f"\n🔍 Program Location Extraction: Identifying BASIC programs...")
        program_list_response = identify_basic_programs(gemini_files, client, debug=args.debug)
        programs = parse_program_list(program_list_response, debug=args.debug)
        
        if not programs:
            print("❌ No programs found in the images.")
            return
        
        print(f"✅ Found {len(programs)} programs:")
        for i, program in enumerate(programs, 1):
            pages_str = ", ".join(map(str, program.get('pages', [])))
            print(f"  {i}. {program['name']} (pages: {pages_str})")
        
        # Save program list to JSON for debugging
        save_program_list_to_json(programs, args.output_dir)
        
        # OPTIMIZATION: Create page-to-file mapping for Program Source Extraction reuse
        print(f"\n🔧 Creating page-to-file mapping for optimized Program Source Extraction...")
        page_to_gemini_file = create_page_to_file_mapping(gemini_files, start_page, debug=args.debug)
        
        # Get unique pages needed for all programs
        unique_pages = get_unique_pages_from_programs(programs)
        available_pages = [page for page in unique_pages if page in page_to_gemini_file]
        missing_pages = [page for page in unique_pages if page not in page_to_gemini_file]
        
        print(f"📊 Program optimization analysis:")
        print(f"  - Programs need {len(unique_pages)} unique pages: {', '.join(map(str, unique_pages))}")
        print(f"  - Available from upload: {len(available_pages)} pages")
        print(f"  - Missing from upload: {len(missing_pages)} pages")
        
        if missing_pages:
            print(f"⚠️  Missing pages will cause some programs to be skipped: {missing_pages}")
        
        # PROGRAM SOURCE EXTRACTION: Extract source code for each program using optimized approach
        print(f"\n📝 Program Source Extraction: Extracting source code for each program (optimized)...")
        saved_files = []
        skipped_programs = []
        failed_programs = []
        
        for i, program in enumerate(programs, 1):
            program_name = program['name']
            page_numbers = program.get('pages', [])
            pages_str = ', '.join(map(str, page_numbers))
            
            print(f"\n📋 ({i}/{len(programs)}) Processing '{program_name}' (pages: {pages_str})...")
            
            if args.debug:
                print(f"🔍 DEBUG: Program '{program_name}' expects {len(page_numbers)} pages: {page_numbers}")
            
            try:
                # Get the specific Gemini files for this program
                files_for_program = []
                missing_pages_for_program = []
                
                for page in page_numbers:
                    if page in page_to_gemini_file:
                        files_for_program.append(page_to_gemini_file[page])
                    else:
                        missing_pages_for_program.append(page)
                
                if args.debug:
                    print(f"🔍 DEBUG: Found files for {len(files_for_program)}/{len(page_numbers)} pages")
                    if missing_pages_for_program:
                        print(f"🔍 DEBUG: Missing pages for '{program_name}': {missing_pages_for_program}")
                
                if not files_for_program:
                    skip_msg = f"No files found for '{program_name}' on pages {page_numbers}"
                    print(f"⚠️  {skip_msg}")
                    skipped_programs.append((program_name, skip_msg))
                    continue
                
                if missing_pages_for_program:
                    print(f"⚠️  Partial data: missing {len(missing_pages_for_program)} pages for '{program_name}': {missing_pages_for_program}")
                
                print(f"🤖 Calling Gemini AI to extract source code...")
                source_code = extract_program_source_optimized(files_for_program, program_name, page_numbers, client, debug=args.debug)
                
                if not source_code.strip():
                    skip_msg = f"Empty response from Gemini for '{program_name}'"
                    print(f"⚠️  {skip_msg}")
                    skipped_programs.append((program_name, skip_msg))
                    continue
                
                output_path = save_program_to_file(program_name, source_code, args.output_dir)
                saved_files.append(output_path)
                print(f"✅ Successfully saved '{program_name}' -> {output_path}")
                
            except Exception as e:
                error_msg = f"Error processing '{program_name}': {e}"
                print(f"❌ {error_msg}")
                failed_programs.append((program_name, str(e)))
                if args.debug:
                    import traceback
                    print(f"🔍 DEBUG: Full traceback for '{program_name}':")
                    traceback.print_exc()
        
        # Final summary for both phases
        print(f"\n🎉 Processing complete!")
        print(f"📊 Summary:")
        print(f"  - Images processed: {len(png_files)}")
        print(f"  - Programs found: {len(programs)}")
        print(f"  - Successfully saved: {len(saved_files)}")
        print(f"  - Skipped (no data): {len(skipped_programs)}")
        print(f"  - Failed (errors): {len(failed_programs)}")
        print(f"  - Output directory: {args.output_dir}")
        
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
        # Clean up uploaded files (only if gemini_files exists)
        if 'gemini_files' in locals():
            print(f"\n🧹 Cleaning up uploaded files...")
            for gemini_file in gemini_files:
                delete_gemini_file(gemini_file.name, client)
            print("✅ Cleanup complete")

if __name__ == "__main__":
    main()
