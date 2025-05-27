#!/bin/bash

# Application-level environment variables
export APP_NAME="MyApp"
export LOG_LEVEL="INFO"
export BASE_PATH="/opt/myapp"

# Main script logic
echo "Starting application: $APP_NAME"
echo "Log level: $LOG_LEVEL"

# Job-level environment variable
export JOB_ID="job_123"
export TIMEOUT="300"

# Process some data
for i in {1..5}; do
    echo "Processing item $i with job ID: $JOB_ID"
    sleep 1
done

# Another job-level variable
export RESULT_PATH="/tmp/results"

echo "Results saved to: $RESULT_PATH"
echo "Job completed successfully"