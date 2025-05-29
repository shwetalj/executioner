# Alternative Methods to Render Mermaid Diagrams

Since mermaid-cli is having Chrome version compatibility issues, here are alternative methods to generate the architecture diagrams:

## Method 1: GitHub Rendering (Recommended if using GitHub)
Simply push the architecture.md file to GitHub. GitHub automatically renders Mermaid diagrams in markdown files.

## Method 2: VS Code Extension
If using VS Code:
1. Install the "Markdown Preview Mermaid Support" extension
2. Open architecture.md
3. Use the preview pane to view rendered diagrams
4. Right-click on diagrams to save as images

## Method 3: Online Mermaid Editor
1. Visit https://mermaid.live/
2. Copy content from each .mmd file in the diagrams/ directory
3. Paste into the editor
4. Use the download button to save as PNG/SVG

## Method 4: Docker-based Rendering
```bash
# Run mermaid-cli in Docker
docker run --rm -v $(pwd):/data minlag/mermaid-cli -i /data/diagrams/diagram-1-system-architecture.mmd -o /data/diagrams/diagram-1-system-architecture.png -t dark -b transparent
```

## Method 5: Node.js Script
Create a simple Node.js script to render using Playwright instead of Puppeteer:

```javascript
// render-mermaid.js
const { chromium } = require('playwright');
const fs = require('fs');

async function renderMermaid(input, output) {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
      <script>mermaid.initialize({ startOnLoad: true, theme: 'dark' });</script>
    </head>
    <body style="background: transparent;">
      <div class="mermaid">
        ${fs.readFileSync(input, 'utf8')}
      </div>
    </body>
    </html>
  `;
  
  await page.setContent(html);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: output, fullPage: true, omitBackground: true });
  await browser.close();
}

// Usage
renderMermaid('diagrams/diagram-1-system-architecture.mmd', 'diagram-1.png');
```

## Method 6: Python with Selenium
```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

def render_mermaid(input_file, output_file):
    with open(input_file, 'r') as f:
        mermaid_code = f.read()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
        <script>mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});</script>
    </head>
    <body style="background: transparent;">
        <div class="mermaid">
            {mermaid_code}
        </div>
    </body>
    </html>
    """
    
    options = Options()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    
    driver.get(f"data:text/html,{html}")
    time.sleep(2)
    driver.save_screenshot(output_file)
    driver.quit()
```

## Extracted Diagrams Available

The following diagram files have been extracted to `/home/sjoshi/claudelab/executioner/docs/diagrams/`:

1. **diagram-1-system-architecture.mmd** - High-level component overview
2. **diagram-2-component-relationships.mmd** - Component relationships
3. **diagram-3-data-flow.mmd** - Data flow between components
4. **diagram-4-execution-flow.mmd** - Main execution process
5. **diagram-5-decision-points.mmd** - Decision points and flow control
6. **diagram-6-job-lifecycle.mmd** - Individual job processing states
7. **diagram-7-job-execution-detail.mmd** - Detailed job execution flow
8. **diagram-8-database-schema.mmd** - Database table relationships
9. **diagram-9-database-operations.mmd** - Database operation sequences
10. **diagram-10-configuration-flow.mmd** - Configuration loading and validation
11. **diagram-11-configuration-structure.mmd** - Configuration file structure

Each file contains the raw Mermaid diagram code that can be rendered using any of the methods above.