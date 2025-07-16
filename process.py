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

def convert_to_png(src_path, dest_dir="png_output"):
    """Converts an image file to PNG format using Pillow, saving to dest_dir."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    png_path = dest_dir / (Path(src_path).stem + ".png")
    
    # Check if PNG already exists
    if png_path.exists():
        print(f"Using cached PNG: {png_path}")
        return png_path
    
    img = Image.open(src_path)
    img.save(png_path, format="PNG", optimize=True)
    print(f"Converted {src_path} -> {png_path}")
    return png_path

def download_images(urls, save_dir="downloads", pause_seconds=0.25):
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    downloaded_files = []
    for url in urls:
        filename = url.split("/")[-1]
        save_path = Path(save_dir) / filename
        
        # Check if file already exists
        if save_path.exists():
            print(f"Using cached file: {save_path}")
        else:
            print(f"Downloading {url} -> {save_path}")
            try:
                response = requests.get(url)
                response.raise_for_status()
                with open(save_path, "wb") as f:
                    f.write(response.content)
                print(f"Downloaded: {save_path}")
                # Only pause after actual downloads to avoid hammering the server
                time.sleep(pause_seconds)
            except Exception as e:
                print(f"Failed to download {url}: {e}")
                continue
        
        try:
            png_path = convert_to_png(save_path)
            downloaded_files.append(png_path)
        except Exception as e:
            print(f"Failed to convert {save_path}: {e}")
        
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

def get_png_paths_for_pages(page_numbers):
    """Map page numbers to their PNG file paths."""
    png_paths = {}
    for page_num in page_numbers:
        png_path = Path("png_output") / f"page{page_num}.png"
        if png_path.exists():
            png_paths[page_num] = png_path
        else:
            print(f"⚠️  PNG file not found for page {page_num}: {png_path}")
    return png_paths

def upload_images_for_pages(page_numbers, client):
    """Upload only the needed images and return page-to-handle mapping."""
    png_paths = get_png_paths_for_pages(page_numbers)
    page_to_gemini_file = {}
    
    print(f"📤 Uploading {len(png_paths)} specific images (pages: {', '.join(map(str, page_numbers))})...")
    
    for page_num, png_path in png_paths.items():
        print(f"Uploading page {page_num}: {png_path}...")
        gemini_file = upload_image_to_gemini(png_path, client)
        page_to_gemini_file[page_num] = gemini_file
    
    print(f"✅ Uploaded {len(page_to_gemini_file)} images successfully")
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
    """Phase 1: Scan all images to identify BASIC program listings and their names."""
    prompt = (
        "PHASE 1: PROGRAM IDENTIFICATION\n\n"
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
    
    print(f"Phase 1: Identifying BASIC programs across {len(files)} images...")
    contents = [prompt] + files
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents
    )
    
    if debug:
        print("\n=== DEBUG: Phase 1 Gemini Response ===")
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
    """Phase 2: Extract source code for a specific program."""
    # Filter files to only include relevant pages
    filtered_files = filter_files_by_pages(files, page_numbers)
    
    pages_str = ", ".join(map(str, page_numbers)) if page_numbers else "all pages"
    prompt = (
        f"PHASE 2: SOURCE CODE EXTRACTION\n\n"
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
    
    print(f"Phase 2: Extracting source code for '{program_name}' (pages: {pages_str}, {len(filtered_files)} images)...")
    contents = [prompt] + filtered_files
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents
    )
    
    if debug:
        print(f"\n=== DEBUG: Phase 2 Response for '{program_name}' ===")
        print(f"Pages: {pages_str}")
        print(f"Filtered files: {len(filtered_files)}/{len(files)}")
        print(response.text)
        print("=== END DEBUG ===\n")
    
    return response.text

def extract_program_source_optimized(files_for_program, program_name, page_numbers, client, debug=False):
    """Phase 2: Extract source code using pre-filtered files (optimized version)."""
    pages_str = ", ".join(map(str, page_numbers)) if page_numbers else "all pages"
    prompt = (
        f"PHASE 2: SOURCE CODE EXTRACTION\n\n"
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
    
    print(f"Phase 2: Extracting source code for '{program_name}' (pages: {pages_str}, {len(files_for_program)} images)...")
    contents = [prompt] + files_for_program
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents
    )
    
    if debug:
        print(f"\n=== DEBUG: Phase 2 Response for '{program_name}' ===")
        print(f"Pages: {pages_str}")
        print(f"Images provided: {len(files_for_program)}")
        print(response.text)
        print("=== END DEBUG ===\n")
    
    return response.text

def parse_program_list(response_text):
    """Parse the JSON response from program identification phase."""
    if not response_text:
        print("Error: Empty response from Gemini")
        return []
    
    try:
        # Extract JSON from markdown code block if present
        json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            json_text = response_text
        
        data = json.loads(json_text)
        return data.get('programs', [])
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Response text: {response_text}")
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

def load_program_list_from_json(json_path):
    """Load program list from JSON file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("programs", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading program list from {json_path}: {e}")
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
        "--phase-1-only",
        action="store_true",
        help="Only run Phase 1 (program identification) and save results to JSON"
    )
    
    parser.add_argument(
        "--phase-2-only",
        action="store_true",
        help="Only run Phase 2 (source extraction) using existing program list JSON"
    )
    
    parser.add_argument(
        "--program-list",
        help="Path to JSON file containing program list (for --phase-2-only)"
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
        png_files = download_images(urls, pause_seconds=args.pause)
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
                    png_path = convert_to_png(gif_path)
                    png_files.append(png_path)
                except Exception as e:
                    print(f"❌ Failed to convert {gif_path}: {e}")
        print(f"✅ Converted {len(png_files)} images")
        return
    
    # Set up Gemini client (API key must be in GEMINI_API_KEY env var)
    client = genai.Client()
    
    # Handle phase-2-only mode differently (no bulk upload needed)
    if args.phase_2_only:
        # Phase 2 only mode handles its own image upload optimization
        pass
    else:
        # Download and convert images (for all other modes)
        print(f"\n📥 Downloading and converting {end_page - start_page + 1} images...")
        urls = generate_atari_image_urls(start=start_page, end=end_page)
        png_files = download_images(urls, pause_seconds=args.pause)
        if not png_files:
            print("❌ No images downloaded.")
            return
        
        print(f"✅ Successfully processed {len(png_files)} images")
        
        # Upload all images to Gemini
        print(f"\n📤 Uploading {len(png_files)} images to Gemini...")
        gemini_files = upload_multiple_images_to_gemini(png_files, client)
        print(f"✅ All images uploaded successfully")
    
    try:
        # Handle phase-1-only mode
        if args.phase_1_only:
            print(f"\n🔍 Phase 1 only: Identifying BASIC programs...")
            program_list_response = identify_basic_programs(gemini_files, client, debug=args.debug)
            programs = parse_program_list(program_list_response)
            
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
        
        # Handle phase-2-only mode (OPTIMIZED)
        if args.phase_2_only:
            if not args.program_list:
                print("❌ --program-list is required for --phase-2-only mode")
                return
            
            print(f"\n📝 Phase 2 only: Loading program list from {args.program_list}")
            programs = load_program_list_from_json(args.program_list)
            
            if not programs:
                print("❌ No programs found in the program list file.")
                return
            
            print(f"✅ Loaded {len(programs)} programs from file")
            
            # OPTIMIZATION: Get unique pages and upload only those
            unique_pages = get_unique_pages_from_programs(programs)
            print(f"📊 Programs need {len(unique_pages)} unique pages: {', '.join(map(str, unique_pages))}")
            
            # Upload only the needed images
            page_to_gemini_file = upload_images_for_pages(unique_pages, client)
            
            if not page_to_gemini_file:
                print("❌ No images could be uploaded.")
                return
            
            try:
                # Extract source code for each program using optimized approach
                saved_files = []
                for i, program in enumerate(programs, 1):
                    program_name = program['name']
                    print(f"\n📋 ({i}/{len(programs)}) Processing '{program_name}'...")
                    
                    try:
                        page_numbers = program.get('pages', [])
                        # Get the specific Gemini files for this program
                        files_for_program = [page_to_gemini_file[page] for page in page_numbers if page in page_to_gemini_file]
                        
                        if not files_for_program:
                            print(f"⚠️  No files found for '{program_name}' on pages {page_numbers}")
                            continue
                        
                        source_code = extract_program_source_optimized(files_for_program, program_name, page_numbers, client, debug=args.debug)
                        output_path = save_program_to_file(program_name, source_code, args.output_dir)
                        saved_files.append(output_path)
                        print(f"✅ Successfully saved '{program_name}'")
                    except Exception as e:
                        print(f"❌ Error processing '{program_name}': {e}")
                
                print(f"\n🎉 Phase 2 complete! Saved {len(saved_files)} programs")
                
            finally:
                # Clean up uploaded files
                print(f"\n🧹 Cleaning up uploaded files...")
                for gemini_file in page_to_gemini_file.values():
                    delete_gemini_file(gemini_file.name, client)
                print("✅ Cleanup complete")
            
            return
        
        # Default: Run both phases
        # PHASE 1: Identify all BASIC programs
        print(f"\n🔍 Phase 1: Identifying BASIC programs...")
        program_list_response = identify_basic_programs(gemini_files, client, debug=args.debug)
        programs = parse_program_list(program_list_response)
        
        if not programs:
            print("❌ No programs found in the images.")
            return
        
        print(f"✅ Found {len(programs)} programs:")
        for i, program in enumerate(programs, 1):
            pages_str = ", ".join(map(str, program.get('pages', [])))
            print(f"  {i}. {program['name']} (pages: {pages_str})")
        
        # Save program list to JSON for debugging
        save_program_list_to_json(programs, args.output_dir)
        
        # PHASE 2: Extract source code for each program
        print(f"\n📝 Phase 2: Extracting source code for each program...")
        saved_files = []
        
        for i, program in enumerate(programs, 1):
            program_name = program['name']
            print(f"\n📋 ({i}/{len(programs)}) Processing '{program_name}'...")
            
            try:
                page_numbers = program.get('pages', [])
                source_code = extract_program_source(gemini_files, program_name, page_numbers, client, debug=args.debug)
                output_path = save_program_to_file(program_name, source_code, args.output_dir)
                saved_files.append(output_path)
                print(f"✅ Successfully saved '{program_name}'")
            except Exception as e:
                print(f"❌ Error processing '{program_name}': {e}")
        
        # Summary
        print(f"\n🎉 Processing complete!")
        print(f"📊 Summary:")
        print(f"  - Images processed: {len(png_files)}")
        print(f"  - Programs found: {len(programs)}")
        print(f"  - Programs saved: {len(saved_files)}")
        print(f"  - Output directory: {args.output_dir}")
        
        if saved_files:
            print(f"\n📁 Saved program files:")
            for file_path in saved_files:
                print(f"  - {file_path}")
    
    finally:
        # Clean up uploaded files (only if gemini_files exists)
        if 'gemini_files' in locals():
            print(f"\n🧹 Cleaning up uploaded files...")
            for gemini_file in gemini_files:
                delete_gemini_file(gemini_file.name, client)
            print("✅ Cleanup complete")

if __name__ == "__main__":
    main()
