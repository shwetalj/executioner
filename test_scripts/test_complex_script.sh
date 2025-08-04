#!/bin/bash

# Application-level environment variables
export APP_NAME="DataProcessor"
export LOG_LEVEL="INFO"
export BASE_PATH="/opt/dataproc"

# Initial setup messages
echo "Starting application: $APP_NAME"
echo "Log level: $LOG_LEVEL"

# Create necessary directories
mkdir -p /tmp/data/input
mkdir -p /tmp/data/output

# Job-level environment variable
export DATA_DIR="/tmp/data"

# Download data files
wget https://example.com/data1.csv -O $DATA_DIR/input/data1.csv
wget https://example.com/data2.csv -O $DATA_DIR/input/data2.csv

# Process data files
for file in $DATA_DIR/input/*.csv; do
    echo "Processing $file"
    python3 process_data.py "$file" "$DATA_DIR/output/$(basename $file)"
done

# Compress results
tar -czf $DATA_DIR/results.tar.gz -C $DATA_DIR/output .

# Upload results
export S3_BUCKET="my-results-bucket"
aws s3 cp $DATA_DIR/results.tar.gz s3://$S3_BUCKET/results_$(date +%Y%m%d).tar.gz

# Cleanup
rm -rf $DATA_DIR

# Final status
echo "Job completed successfully"
echo "Results uploaded to S3"