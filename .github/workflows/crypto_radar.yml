name: Crypto Legal Radar

on:
  schedule:
    # Runs every day at 7:00 AM UTC (12:30 PM IST)
    - cron: "0 7 * * *"
  workflow_dispatch: # Allow manual trigger from GitHub Actions UI

permissions:
  contents: write

jobs:
  publish:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Run Crypto Legal Radar
        run: python scripts/crypto_radar.py

      - name: Commit and push new articles
        run: |
          git config user.name "actions-user"
          git config user.email "actions@github.com"
          git add blog/ blog.html .seen_articles.json
          if git diff --cached --quiet; then
            echo "Nothing to commit. No new articles today."
          else
            git commit -m "Auto-publish: Crypto Legal Radar $(date +'%Y-%m-%d')"
            git push
          fi
