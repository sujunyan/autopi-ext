#!/bin/bash

REMOTE_USER="pi"
# REMOTE_HOST="autopi"
REMOTE_HOST="192.168.124.16"
REMOTE_DATA_PATH="/home/pi/autopi-ext/data/"
LOCAL_DOWNLOAD_PATH="/Users/junyansu/dev/autopi-ext/"

# Ensure the local download directory exists
mkdir -p "$LOCAL_DOWNLOAD_PATH"

echo "Downloading data from $REMOTE_USER@$REMOTE_HOST:$REMOTE_DATA_PATH to $LOCAL_DOWNLOAD_PATH"
# Use scp to download the data. The -r flag is for recursive copy of directories.
# The -p flag preserves modification times, access times, and modes.
# The -i flag specifies the identity file (private key). If not specified, ssh will try default keys.
scp -r -p "$REMOTE_USER"@"$REMOTE_HOST":"$REMOTE_DATA_PATH" "$LOCAL_DOWNLOAD_PATH"

if [ $? -eq 0 ]; then
    echo "Download successful. Deleting data from remote server..."
    # Use ssh to execute the rm command on the remote server.
    # The -i flag specifies the identity file (private key).
    ssh "$REMOTE_USER"@"$REMOTE_HOST" "rm -f ${REMOTE_DATA_PATH}h11/*.txt"
    if [ $? -eq 0 ]; then
        echo "Remote h11 data deleted successfully."
    else
        echo "Error: Failed to delete remote data h11."
    fi
    ssh "$REMOTE_USER"@"$REMOTE_HOST" "rm -f ${REMOTE_DATA_PATH}j1939/*.csv"
    if [ $? -eq 0 ]; then
        echo "Remote j1939 data deleted successfully."
    else
        echo "Error: Failed to delete remote data j1939."
    fi
    
else
    echo "Error: Download failed. Remote data not deleted."
fi