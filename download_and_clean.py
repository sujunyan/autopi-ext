import subprocess
import os
import sys

REMOTE_USER = "pi"
REMOTE_HOST = "192.168.124.16"
REMOTE_DATA_PATH = "/home/pi/autopi-ext/data/"
LOCAL_DOWNLOAD_PATH = "/Users/junyansu/dev/autopi-ext/"

# Subfolders and their respective file extensions to clean up
SUBFOLDERS = {
    "h11": "*.txt",
    "j1939": "*.csv",
    "embedgps": "*.txt",
    "embedacc": "*.txt",
}

def run_command(command):
    """Runs a shell command and returns the return code."""
    print(f"Executing: {command}")
    result = subprocess.run(command, shell=True)
    return result.returncode

def main():
    # Ensure the local download directory exists
    if not os.path.exists(LOCAL_DOWNLOAD_PATH):
        os.makedirs(LOCAL_DOWNLOAD_PATH)
        print(f"Created local directory: {LOCAL_DOWNLOAD_PATH}")

    print(f"Downloading data from {REMOTE_USER}@{REMOTE_HOST}:{REMOTE_DATA_PATH} to {LOCAL_DOWNLOAD_PATH}")
    
    # Use scp to download the data
    # -r: recursive, -p: preserve attributes
    scp_cmd = f'scp -r -p {REMOTE_USER}@{REMOTE_HOST}:{REMOTE_DATA_PATH} "{LOCAL_DOWNLOAD_PATH}"'
    
    if run_command(scp_cmd) == 0:
        print("Download successful. Deleting data from remote server...")
        
        for folder, extension in SUBFOLDERS.items():
            remote_path = os.path.join(REMOTE_DATA_PATH, folder, extension)
            rm_cmd = f'ssh {REMOTE_USER}@{REMOTE_HOST} "rm -f {remote_path}"'
            
            if run_command(rm_cmd) == 0:
                print(f"Remote {folder} data cleaned successfully.")
            else:
                print(f"Error: Failed to clean remote data in {folder}.")
            
    else:
        print("Error: Download failed. Remote data not deleted.")
        sys.exit(1)

if __name__ == "__main__":
    main()
