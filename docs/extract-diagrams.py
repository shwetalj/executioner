#!/usr/bin/env python3
"""
Extract Mermaid diagrams from architecture.md into individual files
that can be rendered separately.
"""

import re
import os

def extract_mermaid_diagrams(input_file, output_dir):
    """Extract all mermaid code blocks from a markdown file."""
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Read the input file
    with open(input_file, 'r') as f:
        content = f.read()
    
    # Find all mermaid code blocks
    mermaid_pattern = r'```mermaid\n(.*?)\n```'
    matches = re.findall(mermaid_pattern, content, re.DOTALL)
    
    # Extract diagram titles from the content
    titles = [
        "system-architecture",
        "component-relationships", 
        "data-flow",
        "execution-flow",
        "decision-points",
        "job-lifecycle",
        "job-execution-detail",
        "database-schema",
        "database-operations",
        "configuration-flow",
        "configuration-structure"
    ]
    
    # Save each diagram
    for i, (diagram, title) in enumerate(zip(matches, titles[:len(matches)])):
        output_file = os.path.join(output_dir, f"diagram-{i+1}-{title}.mmd")
        with open(output_file, 'w') as f:
            f.write(diagram)
        print(f"Extracted: {output_file}")
    
    print(f"\nTotal diagrams extracted: {len(matches)}")
    print("\nTo render these diagrams:")
    print("1. Visit https://mermaid.live/")
    print("2. Copy and paste the content of each .mmd file")
    print("3. Download as PNG/SVG")
    print("\nOr use the mermaid CLI when Chrome is properly installed:")
    print("for file in diagrams/*.mmd; do")
    print('  mmdc -i "$file" -o "${file%.mmd}.png" -t dark -b transparent')
    print("done")

if __name__ == "__main__":
    extract_mermaid_diagrams("architecture.md", "diagrams")