import json
import argparse
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# --- Helper Functions ---

def read_file_content(file_path: str) -> Optional[List[str]]:
    """Reads a file and returns its content as a list of lines or None on error."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.readlines()
    except FileNotFoundError:
        print(f"Error: File not found - {file_path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error reading file {file_path}: {e}", file=sys.stderr)
        return None

def write_file_content(file_path: str, lines: List[str]) -> bool:
    """Writes a list of lines to a file. Returns True on success, False on error."""
    try:
        # Ensure parent directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"Successfully wrote to {file_path}")
        return True
    except Exception as e:
        print(f"Error writing to file {file_path}: {e}", file=sys.stderr)
        return False

# --- Merge Operation Handlers ---

def handle_create_new_or_replace_file(operation: Dict[str, Any], verbose: bool) -> bool:
    """Handles 'create_new' and 'replace_file' operations."""
    output_file = operation.get("output_file")
    source_file = operation.get("source_file")
    segments = operation.get("segments")

    if not output_file:
        print(f"Error: 'output_file' missing for {operation.get('operation')} operation.", file=sys.stderr)
        return False

    content_lines: Optional[List[str]] = None
    operation_type = operation.get('operation')

    if source_file:
        if verbose: print(f"Operation {operation_type}: Reading source file {source_file} for {output_file}")
        content_lines = read_file_content(source_file)
    elif segments and operation_type == 'create_new': # Only create_new from segments, replace_file needs source_file
        if verbose: print(f"Operation {operation_type}: Concatenating segments for {output_file}")
        all_segment_lines: List[str] = []
        for seg_info in segments:
            segment_path = seg_info.get("source")
            if not segment_path:
                print(f"Error: Segment 'source' path missing in {operation_type} for {output_file}.", file=sys.stderr)
                return False
            seg_lines = read_file_content(segment_path)
            if seg_lines is None: return False # Error already printed
            all_segment_lines.extend(seg_lines)
        content_lines = all_segment_lines
    else:
        print(f"Error: For '{operation_type}', 'source_file' or 'segments' (for create_new) must be specified.", file=sys.stderr)
        return False

    if content_lines is None:
        # Error reading source or segments
        return False

    if verbose: print(f"Writing content to {output_file}")
    return write_file_content(output_file, content_lines)


def handle_concatenate(operation: Dict[str, Any], verbose: bool) -> bool:
    """Handles 'concatenate' operation."""
    output_file = operation.get("output_file")
    segments = operation.get("segments")

    if not output_file or not segments:
        print("Error: 'output_file' and 'segments' are required for 'concatenate' operation.", file=sys.stderr)
        return False

    all_lines: List[str] = []
    if verbose: print(f"Operation concatenate: Preparing to merge segments into {output_file}")
    for seg_info in segments:
        segment_path = seg_info.get("source")
        if not segment_path:
            print(f"Error: Segment 'source' path missing in concatenate for {output_file}.", file=sys.stderr)
            return False
        if verbose: print(f"  Reading segment: {segment_path}")
        seg_lines = read_file_content(segment_path)
        if seg_lines is None: return False # Error already printed
        all_lines.extend(seg_lines)

    if verbose: print(f"Writing concatenated content to {output_file}")
    return write_file_content(output_file, all_lines)

def handle_replace_block_by_markers(operation: Dict[str, Any], verbose: bool) -> bool:
    """Handles 'replace_block_by_markers' operation."""
    output_file = operation.get("output_file")
    base_file = operation.get("base_file")
    segment_file = operation.get("segment_file")
    start_marker = operation.get("start_marker")
    end_marker = operation.get("end_marker")

    if not all([output_file, base_file, segment_file, start_marker, end_marker]):
        print("Error: 'output_file', 'base_file', 'segment_file', 'start_marker', and 'end_marker' are required for 'replace_block_by_markers'.", file=sys.stderr)
        return False

    if verbose: print(f"Operation replace_block_by_markers: Modifying {base_file} to create {output_file}")
    base_lines = read_file_content(base_file)
    segment_lines = read_file_content(segment_file)

    if base_lines is None or segment_lines is None: return False

    try:
        start_idx = -1
        end_idx = -1
        for i, line in enumerate(base_lines):
            if start_marker in line: # Simple string containment
                start_idx = i
            if end_marker in line and start_idx != -1 : # Ensure end_marker is after start_marker
                end_idx = i
                break # Found both

        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx :
            print(f"Error: Markers not found or in wrong order in {base_file}. Start: '{start_marker}', End: '{end_marker}'.", file=sys.stderr)
            print(f"  (Found start at line {start_idx+1}, end at line {end_idx+1})", file=sys.stderr)
            return False

        if verbose: print(f"  Found start_marker '{start_marker}' at line {start_idx + 1}")
        if verbose: print(f"  Found end_marker '{end_marker}' at line {end_idx + 1}")

        # Current logic: replace the block including the lines with the markers
        new_lines = base_lines[:start_idx] + segment_lines + base_lines[end_idx + 1:]
        if verbose: print(f"  Replacing lines from {start_idx + 1} to {end_idx + 1} with content from {segment_file}")

    except ValueError: # Should not happen with current logic, but good for robustness
        print(f"Error processing markers in {base_file}. Start: '{start_marker}', End: '{end_marker}'.", file=sys.stderr)
        return False

    if verbose: print(f"Writing modified content to {output_file}")
    return write_file_content(output_file, new_lines)


def handle_insert_line_operation(operation: Dict[str, Any], verbose: bool, before: bool) -> bool:
    """Handles 'insert_after_line' or 'insert_before_line' operations."""
    output_file = operation.get("output_file")
    base_file = operation.get("base_file")
    segment_file = operation.get("segment_file")
    line_content_marker = operation.get("line_content") # The exact string content of the line

    if not all([output_file, base_file, segment_file, line_content_marker]):
        print(f"Error: 'output_file', 'base_file', 'segment_file', and 'line_content' are required for insert operation.", file=sys.stderr)
        return False

    op_name = "insert_before_line" if before else "insert_after_line"
    if verbose: print(f"Operation {op_name}: Modifying {base_file} to create {output_file}")

    base_lines = read_file_content(base_file)
    segment_lines = read_file_content(segment_file)

    if base_lines is None or segment_lines is None: return False

    insert_idx = -1
    line_content_marker_stripped = line_content_marker.strip('\n\r')

    for i, line in enumerate(base_lines):
        if line.strip('\n\r') == line_content_marker_stripped:
            insert_idx = i
            break

    if insert_idx == -1:
        print(f"Error: Marker line '{line_content_marker_stripped}' not found in {base_file}.", file=sys.stderr)
        return False

    if verbose: print(f"  Found marker line '{line_content_marker_stripped}' at line {insert_idx + 1}")

    if before:
        new_lines = base_lines[:insert_idx] + segment_lines + base_lines[insert_idx:]
        if verbose: print(f"  Inserting content from {segment_file} before line {insert_idx + 1}")
    else: # after
        new_lines = base_lines[:insert_idx+1] + segment_lines + base_lines[insert_idx+1:]
        if verbose: print(f"  Inserting content from {segment_file} after line {insert_idx + 1}")

    if verbose: print(f"Writing modified content to {output_file}")
    return write_file_content(output_file, new_lines)


# --- Main Script Logic ---
def main():
    parser = argparse.ArgumentParser(description="Merges file segments based on a JSON configuration.")
    parser.add_argument(
        "-c", "--config",
        default="merge_config.json",
        help="Path to the merge configuration JSON file (default: merge_config.json in current dir)."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output."
    )
    args = parser.parse_args()

    verbose = args.verbose # Assign to local variable for easier use
    if verbose: print(f"Using merge configuration file: {args.config}")

    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found - {args.config}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file {args.config}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading configuration file {args.config}: {e}", file=sys.stderr)
        sys.exit(1)

    merge_operations = config_data.get("merges")
    if not isinstance(merge_operations, list):
        print("Error: Configuration JSON must contain a 'merges' list.", file=sys.stderr)
        sys.exit(1)

    all_successful = True
    for i, operation in enumerate(merge_operations):
        op_type = operation.get("operation")
        if verbose: print(f"\nProcessing operation {i+1}: {op_type}")

        success = False
        if op_type in ["create_new", "replace_file"]:
            success = handle_create_new_or_replace_file(operation, verbose)
        elif op_type == "concatenate":
            success = handle_concatenate(operation, verbose)
        elif op_type == "replace_block_by_markers":
            success = handle_replace_block_by_markers(operation, verbose)
        elif op_type == "insert_after_line":
            success = handle_insert_line_operation(operation, verbose, before=False)
        elif op_type == "insert_before_line":
            success = handle_insert_line_operation(operation, verbose, before=True)
        else:
            print(f"Error: Unknown operation type '{op_type}' in operation {i+1}.", file=sys.stderr)
            all_successful = False # Mark as overall failure

        if not success:
            all_successful = False # Mark as overall failure
            print(f"Operation {i+1} ({op_type or 'Unknown'}) FAILED.", file=sys.stderr) # Added 'Unknown' for safety
        elif verbose:
            print(f"Operation {i+1} ({op_type}) completed successfully.")

    if all_successful:
        print("\nAll merge operations completed successfully.")
        sys.exit(0)
    else:
        print("\nOne or more merge operations failed.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
