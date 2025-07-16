# Atari Basic Book Scan Tools

This repository contains scripts to extract BASIC program listings from old Atari Basic book scans. The scripts download, convert, and process images of program listings from classic Atari books using AI-powered OCR transcription with a sophisticated two-phase extraction system.

## Features

- **Two-Phase Processing**: Separates program identification from source code extraction
- **Automated Downloads**: Downloads GIF images from Atari Archives book scans
- **Image Conversion**: Converts GIF files to PNG format for processing
- **AI-Powered OCR**: Uses Google Gemini to transcribe BASIC programs from scanned images
- **Individual Program Files**: Creates separate markdown files for each BASIC program
- **Smart Caching**: Skips re-downloading/converting existing files
- **Debug Mode**: Comprehensive debugging and phase-specific execution options
- **Progress Indicators**: Clear visual feedback with emoji-based status messages
- **JSON Persistence**: Save/load program lists for debugging and workflow management

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

### Two-Phase Processing Workflow

The script uses a sophisticated two-phase approach:

1. **Phase 1**: Identify all BASIC programs across all pages
2. **Phase 2**: Extract source code for each individual program

### Basic Usage
```bash
# Full processing (both phases)
python process.py --start 1 --end 25    # Process pages 1-25 (recommended for testing)
python process.py --start 1 --end 185   # Process entire book (75 programs)
python process.py --help                # Show help message
```

### Phase-Specific Processing
```bash
# Phase 1 only: Identify all programs
python process.py --start 1 --end 25 --phase-1-only --output-dir results

# Phase 2 only: Extract source code using existing program list
python process.py --phase-2-only --program-list results/program_list.json --output-dir results
```

### Debug and Development Options
```bash
# Debug mode with verbose output
python process.py --start 1 --end 5 --debug

# Download and convert only
python process.py --start 1 --end 25 --download-only
python process.py --start 1 --end 25 --convert-only
```

### Command Line Options

#### Basic Options
- `--start START`: Start page number (default: 1)
- `--end END`: End page number (default: 10)  
- `--page PAGE`: Process a specific page only (overrides --start and --end)
- `--output-dir DIR`: Output directory for files (default: transcriptions)
- `--pause SECONDS`: Pause between downloads in seconds (default: 0.25)

#### Phase-Specific Options
- `--phase-1-only`: Only run Phase 1 (program identification) and save results to JSON
- `--phase-2-only`: Only run Phase 2 (source extraction) using existing program list
- `--program-list FILE`: Path to JSON file containing program list (required for --phase-2-only)

#### Debug Options
- `--debug`: Enable debug output including full Gemini responses
- `--download-only`: Only download and convert images, then exit
- `--convert-only`: Only convert existing GIF files to PNG, then exit

## Output Structure

```
ataritest/
├── downloads/              # Downloaded GIF files
├── png_output/             # Converted PNG files
├── full_book_programs/     # Complete extraction results
│   ├── program_list.json   # Phase 1 output: identified programs
│   ├── acey-ducey.md       # Individual program files
│   ├── amazing.md
│   ├── animal.md
│   └── ...                 # 75 total programs
├── process.py              # Main script
├── requirements.txt        # Dependencies
└── README.md              # This file
```

## Example Workflow

### Complete Book Processing (Recommended)
```bash
# Step 1: Identify all programs (Phase 1)
python process.py --start 1 --end 185 --phase-1-only --output-dir full_book_programs

# Step 2: Extract source code for all programs (Phase 2)
python process.py --phase-2-only --program-list full_book_programs/program_list.json --output-dir full_book_programs
```

### Testing with Smaller Batches
```bash
# Test with first 25 pages
python process.py --start 1 --end 25 --output-dir test_results

# Debug a specific issue
python process.py --start 1 --end 5 --debug --output-dir debug_test
```

## Example Output

### Phase 1 Output (program_list.json)
```json
{
  "programs": [
    {
      "name": "Acey Ducey",
      "pages": [2],
      "description": "Simulation of the Acey Ducey card game..."
    },
    {
      "name": "Amazing",
      "pages": [3],
      "description": "Generates different mazes with guaranteed single path..."
    }
  ]
}
```

### Phase 2 Output (Individual Program Files)
Each program gets its own markdown file:
```markdown
# Acey Ducey

```basic
10 PRINT TAB(28);"ACEY DUCEY CARD GAME"
20 PRINT TAB(15);"CREATIVE COMPUTING MORRISTOWN, NEW JERSEY"
30 PRINT
...
```

## Results

The complete Atari Basic Games book processing yields:
- **75 BASIC programs** extracted from 184 pages
- **Individual markdown files** for each program
- **Complete source code** with proper formatting and line numbers
- **Program metadata** including page numbers and descriptions

## Scripts

- `process.py`: Main script with two-phase processing, debugging, and workflow management features
