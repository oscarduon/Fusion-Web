#!/bin/bash
cd /home/oscar/fusion_web
git pull origin main
cd frontend
npm install
npm run build
# We don't restart uvicorn because we will run it with --reload
