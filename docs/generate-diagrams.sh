#!/bin/bash

# Script to generate PNG images from Mermaid diagrams in architecture.md
# Requires: npm install -g @mermaid-js/mermaid-cli

echo "Generating architecture diagrams..."

# Create images directory
mkdir -p docs/images

# Extract and convert individual diagrams
# You can run this after installing mermaid-cli

echo "To use this script:"
echo "1. Install mermaid CLI: npm install -g @mermaid-js/mermaid-cli"
echo "2. Run: bash docs/generate-diagrams.sh"
echo ""
echo "Or view diagrams online:"
echo "1. Copy mermaid blocks from docs/architecture.md"
echo "2. Paste into https://mermaid.live/"
echo "3. Download as PNG/SVG"
echo ""
echo "Or push to GitHub - it renders Mermaid automatically!"