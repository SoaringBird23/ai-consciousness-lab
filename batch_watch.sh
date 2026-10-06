#!/bin/bash
cd "$(dirname "$0")"
while true; do
  {
    echo "########## $(date '+%F %T') ##########"
    ./venv/bin/python analyze_batches.py 2>&1
    echo
  } >> batch_report.txt
  sleep 600
done
