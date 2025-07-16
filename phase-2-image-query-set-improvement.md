# Phase 2 Image Query Set Performance Improvements

## Summary of Performance Issue

In the current implementation of `process.py`, Phase 2 (source extraction) uploads **all images** in the specified page range to Gemini, regardless of which images are actually needed for the programs listed in the program list JSON. This results in unnecessary uploads, increased API usage, and slower performance, especially when only a subset of pages is required for extraction.

### Key Observations
- **All images in the range are uploaded** before Phase 2, even if only a few are needed.
- **Each program** in the program list may only require a small subset of pages.
- **After processing**, all uploaded files are deleted, but the upload overhead is still incurred every run.

## Proposed Solution: "Phase 2 Image Query Set"

### Goals
- **Upload only the images needed** for the programs in the program list.
- **Upload each image only once** per run.
- **Map page numbers to Gemini file handles** for efficient lookup.
- **Delete all uploaded files** after all programs are processed.

### Step-by-Step Plan

1. **Load the program list JSON** as usual.
2. **Extract all unique page numbers** needed for all programs in the list.
    - Example: If program A needs [2, 3], program B needs [3, 5], the set is {2, 3, 5}.
3. **Map page numbers to file paths** (e.g., `png_output/page2.png`).
4. **Upload only those images** to Gemini, and keep a mapping from page number to Gemini file handle.
5. **For each program:**
    - Use the Gemini file handles for the pages that program needs (in the correct order).
    - Run the Gemini query.
6. **After all programs are processed, delete all uploaded files.**

---

## Pseudocode for the Optimized Phase 2

```python
# 1. Extract unique page numbers from all programs
unique_pages = get_unique_pages_from_programs(programs)

# 2. Map page numbers to PNG file paths
png_paths = get_png_paths_for_pages(unique_pages)

# 3. Upload only needed images and keep a mapping
page_to_gemini_file = {}
for page, png_path in zip(unique_pages, png_paths):
    gemini_file = upload_image_to_gemini(png_path, client)
    page_to_gemini_file[page] = gemini_file

try:
    # 4. For each program, use only the needed Gemini files
    for program in programs:
        needed_pages = program.get('pages', [])
        files_for_program = [page_to_gemini_file[page] for page in needed_pages]
        # ... call extract_program_source(files_for_program, ...) ...
finally:
    # 5. Cleanup: delete all uploaded Gemini files
    for gemini_file in page_to_gemini_file.values():
        delete_gemini_file(gemini_file.name, client)
```

---

## Benefits
- **Reduces upload time** by only uploading what is needed.
- **Minimizes API usage** and potential costs.
- **Speeds up Phase 2** significantly, especially for large books or partial program extraction.

---

## Next Steps
- Integrate this logic into the `--phase-2-only` block of `process.py`.
- Test with both full and partial program lists to ensure correctness and performance gains.

---

*This document captures the investigation and proposed solution for improving Phase 2 performance. Use this as a reference for future refactoring.* 