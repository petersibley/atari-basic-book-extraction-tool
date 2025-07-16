# Atari BASIC Book Extraction Tools

Scripts for extracting Atari BASIC program listings from scanned book images using Google Gemini AI.

## Features

- **Two-Step Extraction:**
  - **Program Location Extraction:** Identify all BASIC programs and their page ranges.
  - **Program Source Extraction:** Extract source code for each program.
- **Automated Download & Conversion:** Fetches GIFs from AtariArchives, converts to PNG.
- **AI OCR:** Uses Gemini for program identification and code extraction.
- **Output:** Individual markdown files per program, plus a JSON index.
- **Smart Caching:** Skips already-downloaded/converted files.
- **Verbose & Step Control:** Run extraction steps independently, verbose output, or just download/convert.

## Requirements

- Python 3.7+
- `pip install -r requirements.txt`
- Gemini API key (see below)

### Python/macOS Quick Setup

- [Install Homebrew](https://brew.sh/) (macOS package manager)
- [Install Python via Homebrew](https://docs.brew.sh/Homebrew-and-Python)
- [Create and use a Python virtual environment](https://docs.python.org/3/library/venv.html)

Example:
```bash
brew install python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Obtain a Gemini API Key
- Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
- Official docs: [Get an API key](https://ai.google.dev/gemini-api/docs/api-key)
- Set your key in your shell:
  ```bash
  export GEMINI_API_KEY="your_api_key_here"
  ```

## Usage

### Typical Workflow

```bash
# Program Location Extraction: Identify programs (pages 1-25)
python process.py --start 1 --end 25 --locate-programs-only --output-dir results

# Program Source Extraction: Extract code for all programs found
python process.py --extract-source-only --program-list results/program_list.json --output-dir results
```

### All-in-One (both extraction steps, pages 1-10 by default)

```bash
python process.py
```

### Options

- `--start N` / `--end N`: Page range (default: 1–10)
- `--output-dir DIR`: Output directory (default: transcriptions)
- `--download-pause SECONDS`: Delay between downloads (default: 0.25)
- `--locate-programs-only`: Only identify programs, save JSON
- `--extract-source-only`: Only extract code (requires `--program-list`)
- `--program-list FILE`: JSON file from program location extraction
- `--download-images-only`: Download/convert images, then exit
- `--convert-images-only`: Convert GIFs to PNG, then exit
- `--verbose`: Verbose Gemini output

## Output

- **downloads/**: GIFs
- **png_output/**: PNGs
- **[output-dir]/**: 
  - `program_list.json`: Program metadata (program location extraction)
  - `*.md`: One file per program (program source extraction)

## Example Output

**program_list.json**
```json
{
  "programs": [
    {
      "name": "Acey Ducey",
      "pages": [2],
      "description": "Simulation of the Acey Ducey card game."
    }
  ]
}
```

**acey-ducey.md**
```markdown
# Acey Ducey

```basic
10 PRINT TAB(28);"ACEY DUCEY CARD GAME"
...
```
```

## Notes

- Requires a valid Gemini API key ([get one here](https://aistudio.google.com/app/apikey)).
- Cleans up uploaded files after processing.
- For full book: use `--start 1 --end 185`.
