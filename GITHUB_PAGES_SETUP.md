# GitHub Pages Setup Instructions

## Prerequisites
- Your repository must be public (or you need GitHub Pro for private repos)
- You need admin access to the repository settings

## Setup Steps

### 1. Enable GitHub Pages in Repository Settings
1. Go to your repository on GitHub
2. Click on **Settings** tab
3. Scroll down to **Pages** section (in the left sidebar under "Code and automation")
4. Under **Source**, select **GitHub Actions**
5. Save the changes

### 2. Commit and Push the Workflow
```bash
# Add the new workflow file
git add .github/workflows/deploy.yml

# Commit the changes
git commit -m "Add GitHub Actions workflow for GitHub Pages deployment"

# Push to GitHub
git push origin main
```

### 3. Verify the Deployment
1. Go to the **Actions** tab in your GitHub repository
2. You should see the "Deploy to GitHub Pages" workflow running
3. Wait for it to complete (usually takes 2-3 minutes)
4. Once successful, your site will be available at:
   ```
   https://[your-github-username].github.io/executioner/
   ```

### 4. Check Deployment Status
- Go to **Settings** → **Pages**
- You should see a green checkmark and the URL where your site is published
- Click "Visit site" to see your deployed application

## How It Works

The workflow automatically:
1. Triggers on every push to the `main` branch
2. Sets up Node.js environment
3. Installs dependencies from `package-lock.json`
4. Builds the Vue application with Vite
5. Deploys the `dist` folder to GitHub Pages

## Troubleshooting

### If the workflow fails:
1. Check the **Actions** tab for error messages
2. Ensure `package-lock.json` exists (run `npm install` locally if needed)
3. Verify all dependencies are correctly listed in `package.json`

### If the site doesn't load:
1. Check that the base path in `vite.config.js` matches your repository name
2. Clear your browser cache
3. Wait a few minutes for GitHub Pages to propagate changes

## Manual Deployment Trigger
You can also manually trigger the deployment:
1. Go to **Actions** tab
2. Select "Deploy to GitHub Pages" workflow
3. Click "Run workflow" button
4. Select the branch and click "Run workflow"

## Local Testing
To test the production build locally:
```bash
cd webinterface
npm run build
npm run preview
```

This will serve the production build locally so you can verify everything works before pushing.