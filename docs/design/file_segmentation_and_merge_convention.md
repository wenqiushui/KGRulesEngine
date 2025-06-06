# File Segmentation and Merge Convention for KCE Development

## 1. Purpose

This document outlines a convention for generating or modifying large or complex files within the Knowledge-CAD-Engine (KCE) project. It is primarily designed to work around limitations where automated tools (like an AI coding assistant) cannot reliably write or modify large/complex files (especially Python scripts with significant indentation and special characters, or existing files requiring precise in-place edits) in a single operation.

The strategy involves:
1.  Breaking down the desired file content into smaller, manageable **segments**.
2.  Storing these segments as individual temporary files.
3.  Using a dedicated Python script (`merge_script.py`) to assemble these segments into the final target file(s) based on instructions in a configuration file (`merge_config.json`).

## 2. The Merge Configuration File (`merge_config.json`)

This JSON file defines a list of merge operations to be performed by `merge_script.py`.

**Structure:**

```json
{
  "merges": [
    {
      "output_file": "path/to/final/target_file.ext",
      "operation": "create_new|replace_file|concatenate|replace_block_by_markers|insert_after_line|insert_before_line",
      "segments": [ // Required for 'concatenate', 'create_new' (if from multiple segments)
        {"source": "temp_merge/segment1.part"},
        {"source": "temp_merge/segment2.part"}
      ],
      "source_file": "temp_merge/full_content.part", // Required for 'replace_file', or for 'create_new' if single source
      "base_file": "path/to/existing/target_file.ext", // Required for 'replace_block_by_markers', 'insert_after_line', 'insert_before_line'
      "segment_file": "temp_merge/block_to_insert.part", // Required for 'replace_block_by_markers', 'insert_after_line', 'insert_before_line'
      "start_marker": "# KCE_MERGE_START <unique_block_id>", // For 'replace_block_by_markers'
      "end_marker": "# KCE_MERGE_END <unique_block_id>",   // For 'replace_block_by_markers'
      "line_content": "unique string content of the line to insert after/before" // For 'insert_after_line', 'insert_before_line'
    }
    // ... more merge operations
  ]
}
```

**Fields:**

*   `merges`: (Array) A list of merge operation objects.
*   Each merge operation object contains:
    *   `output_file`: (String) Path to the final target file that will be created or modified.
    *   `operation`: (String) The type of merge operation to perform. Valid values:
        *   `create_new`: Creates `output_file` using content from `source_file` (if specified) or by concatenating files listed in `segments`. If `output_file` exists, it will be overwritten.
        *   `replace_file`: Identical to `create_new` using `source_file`. Overwrites `output_file` if it exists.
        *   `concatenate`: Creates `output_file` by concatenating all files listed in `segments` in the given order. Overwrites `output_file` if it exists.
        *   `replace_block_by_markers`: Modifies `base_file`. Replaces the content between `start_marker` and `end_marker` (inclusive of markers or exclusive, TBD by script logic - recommend exclusive of markers) with the content of `segment_file`. The result is written to `output_file` (which can be the same as `base_file`).
        *   `insert_after_line`: Modifies `base_file`. Inserts the content of `segment_file` *after* the first line found in `base_file` that exactly matches `line_content`. The result is written to `output_file`.
        *   `insert_before_line`: Modifies `base_file`. Inserts the content of `segment_file` *before* the first line found in `base_file` that exactly matches `line_content`. The result is written to `output_file`.
    *   `segments`: (Array of Objects) Required for `concatenate`. Each object has a `source` key pointing to a segment file path. Order is preserved.
    *   `source_file`: (String) Required for `create_new` (if single source) or `replace_file`. Path to the file whose content will become the `output_file`.
    *   `base_file`: (String) Required for `replace_block_by_markers`, `insert_after_line`, `insert_before_line`. Path to the existing file that will be read and modified.
    *   `segment_file`: (String) Required for `replace_block_by_markers`, `insert_after_line`, `insert_before_line`. Path to the file containing the new content to be inserted/used for replacement.
    *   `start_marker`: (String) Required for `replace_block_by_markers`. A unique string that marks the beginning of the block to be replaced in `base_file`.
    *   `end_marker`: (String) Required for `replace_block_by_markers`. A unique string that marks the end of the block to be replaced.
    *   `line_content`: (String) Required for `insert_after_line` and `insert_before_line`. The exact string content of the line to find in `base_file`.

## 3. Marker Conventions (for `replace_block_by_markers`)

To reliably replace blocks of text/code, files targeted for such modification should use clear, unique markers.

*   **Format:** Markers should be comments appropriate for the file type.
    *   Python: `# KCE_MERGE_START <unique_block_id>` and `# KCE_MERGE_END <unique_block_id>`
    *   YAML: `# KCE_MERGE_START <unique_block_id>` and `# KCE_MERGE_END <unique_block_id>`
    *   JSON: JSON doesn't support comments. This operation is less suitable for direct JSON modification unless it's line-based or the JSON structure is parsed and modified by the script (which is more advanced). For replacing entire JSON files, `replace_file` is better.
    *   TTL/SPARQL: `# KCE_MERGE_START <unique_block_id>` and `# KCE_MERGE_END <unique_block_id>`
    *   Markdown: `<!-- KCE_MERGE_START <unique_block_id> -->` and `<!-- KCE_MERGE_END <unique_block_id> -->`
*   `<unique_block_id>`: A descriptive and unique identifier for the block (e.g., `IMPORTS`, `CLI_INIT_FUNCTION`, `NODE_XYZ_DEFINITION`).
*   **Placement:** Markers should be on their own lines.
*   **Replacement Logic:** The `merge_script.py` should ideally replace the content *between* the start and end markers, leaving the markers themselves in place for future operations, or remove the markers along with the old block and insert the new content without the markers. For simplicity, replacing the block *including* the markers and then writing the new segment (which might not contain markers) is often easiest. The script's behavior here needs to be clearly defined. (Recommendation: replace including markers, new segment does not need to redefine markers unless it's a placeholder for a future nested replacement).

## 4. File Type Handling Considerations

*   **Python (`.py`):**
    *   Indentation is critical. Segments must be generated with correct indentation relative to their insertion point or when concatenated.
    *   When replacing a block, the new segment must integrate seamlessly.
    *   It's often best to replace entire functions or classes if possible, or ensure segments are at a consistent indentation level if concatenating to form a larger script.
*   **YAML (`.yaml`, `.yml`):**
    *   Indentation and list/dictionary structure are key.
    *   Concatenating YAML files is only valid if they are separate documents (using `---`) or if the concatenation results in a valid larger structure.
    *   Replacing blocks needs care to maintain overall YAML validity.
*   **JSON (`.json`):**
    *   Strict syntax. Concatenation is generally invalid unless files are fragments of a larger JSON array/object and the script wraps them correctly.
    *   `replace_file` is usually the safest for JSON.
    *   Modifying JSON by replacing textual blocks is highly risky; the script would ideally parse the JSON, modify it, and then re-serialize.
*   **Turtle/TTL (`.ttl`):**
    *   Prefix definitions are important. If concatenating, ensure prefixes are compatible or defined in each segment/managed globally.
    *   Statements are generally line-independent, making concatenation or block replacement more feasible than Python.
*   **Markdown (`.md`):**
    *   Generally robust for concatenation and block replacement.

## 5. Workflow

1.  **AI Assistant (Jules) Identifies Need:** When a large file needs creation or complex modification, Jules will use the segmentation strategy.
2.  **Jules Generates Segments:**
    *   Jules will generate the content for one or more segment files.
    *   These files will notionally be placed in a `temp_merge/` directory (the AI will list their names and content).
3.  **Jules Provides `merge_config.json` Data:** Jules will provide the JSON object structure that should go into `merge_config.json\` to instruct `merge_script.py`.
4.  **User Creates/Updates Files:**
    *   User creates the segment files in `temp_merge/` with the content provided by Jules.
    *   User creates/updates `merge_config.json` with the data provided by Jules.
5.  **User Runs `merge_script.py`:**
    *   The user executes `python scripts/merge_script.py --config merge_config.json` (or similar invocation).
    *   The script performs the merge operations, creating/modifying the target file(s).
    *   The user should check the output of the script for any errors.
6.  **User Verifies Target File(s):** The user inspects the generated/modified file(s) to ensure correctness.
7.  **Cleanup (Optional):** The user may delete files from `temp_merge/` after successful merging.

## 6. `merge_script.py` (High-Level Functionality)

The `merge_script.py` (to be developed in a subsequent step) should:
*   Accept a path to `merge_config.json` as a command-line argument.
*   Read and parse `merge_config.json`.
*   Iterate through the `merges` array.
*   For each operation:
    *   Read necessary source/segment/base files.
    *   Perform the specified merge logic (concatenation, block replacement, insertion).
    *   Write the result to the `output_file`.
    *   Handle file I/O errors gracefully.
    *   Provide informative print messages about its actions and any errors.

This convention aims to make complex file manipulations manageable and less error-prone when using tools with limitations in direct, large-scale file editing.
