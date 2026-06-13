#!/usr/bin/env bash
set -e

apt-get update -y
apt-get install -y tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng

pip install -r requirements.txt
