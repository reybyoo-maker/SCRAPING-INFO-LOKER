# INFO LOKER website setup

## Run from Terminal

1. Clone the repository and enter the folder:

   \`\`\`bash
   git clone https://github.com/reybyoo-maker/SCRAPING-INFO-LOKER.git
   cd SCRAPING-INFO-LOKER
   \`\`\`

2. Start a local web server:

   \`\`\`bash
   python3 -m http.server 8000
   \`\`\`

3. Open http://localhost:8000 in a browser. Leave the terminal process running while using the site. Serve the folder over HTTP rather than opening index.html directly, so the browser can load the JSON data files.

## Publish

In the GitHub repository, open Settings → Pages, choose GitHub Actions as the build and deployment source, and save if Pages has not previously been enabled. The workflow at .github/workflows/deploy-pages.yml validates the site script and JSON dataset, then deploys the website. The first successful deployment will provide the public Pages URL in the workflow summary and the github-pages environment.

The website loads data/jobs.json and config/locations.json from the published repository, so scraper commits update the website automatically through the deployment workflow.
