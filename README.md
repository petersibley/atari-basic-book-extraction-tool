# Atari Basic Book Scan Tools

This repository contains scripts to extract BASIC program listings from old Atari Basic book scans. The scripts download, convert, and process images of program listings from classic Atari books using AI-powered OCR transcription.

## Features

- **Automated Downloads**: Downloads GIF images from Atari Archives book scans
- **Image Conversion**: Converts GIF files to PNG format for processing
- **AI-Powered OCR**: Uses Google Gemini to transcribe BASIC programs from scanned images
- **Markdown Output**: Saves transcribed programs to organized markdown files
- **Smart Caching**: Skips re-downloading/converting existing files
- **File Management**: Automatically creates directory structure for organized output

## Tech Stack

- **Python**: Core scripting and automation
- **Google Gemini**: AI-powered OCR and text extraction
- **Pillow (PIL)**: Image processing and conversion
- **Requests**: HTTP downloads

## Prerequisites

1. Python 3.7+ with virtual environment
2. Google Gemini API key set in `GEMINI_API_KEY` environment variable
3. Required Python packages (see `requirements.txt`)

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up your Gemini API key:
   ```bash
   export GEMINI_API_KEY="your_api_key_here"
   ```

## Usage

### Basic Usage
```bash
python process.py                    # Process pages 1-10 (default)
python process.py --help            # Show help message
```

### Command Line Options
```bash
python process.py --page 5          # Process only page 5
python process.py --start 1 --end 5 # Process pages 1-5
python process.py --output-dir docs # Save to docs/ directory
python process.py --pause 1.0       # Set 1 second pause between downloads
```

### Available Arguments
- `--start START`: Start page number (default: 1)
- `--end END`: End page number (default: 10)  
- `--page PAGE`: Process a specific page only (overrides --start and --end)
- `--output-dir DIR`: Output directory for markdown files (default: transcriptions)
- `--pause SECONDS`: Pause between downloads in seconds (default: 0.5)

The script will:
1. Download specified pages from the Atari Basic book archives
2. Convert GIF images to PNG format
3. Process one page with Google Gemini OCR
4. Save the transcribed content to `[output-dir]/page_XX.md`
5. Display the file path and transcription results

## Output Structure

```
ataritest/
├── downloads/          # Downloaded GIF files
├── png_output/         # Converted PNG files
├── transcriptions/     # Transcribed markdown files
│   ├── page_01.md
│   ├── page_02.md
│   └── ...
├── process.py          # Main script
└── requirements.txt    # Dependencies
```

## Example Output

For a page containing a BASIC program, the script generates a markdown file with:
- Program title and description
- Complete BASIC code listing with line numbers
- Example gameplay or usage instructions
- Copyright and attribution information

## Scripts

- `process.py`: Main script for downloading, converting, and transcribing Atari Basic book pages
