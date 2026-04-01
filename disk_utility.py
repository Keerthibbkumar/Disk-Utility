import os
import subprocess
import sys
from datetime import datetime
import concurrent.futures
import argparse

run_command = "\033[1m\033[93mExample: python3 disk_utility.py -r ap-mumbai-1"

parser = argparse.ArgumentParser(
    description="Simple script to clean up logs from servers that are running low space on storage servers",
    epilog=run_command
)
parser.add_argument('-r', '--region', type=str, required=True, help='Specify the region name')
args = parser.parse_args()

REGIONS_NAME = args.region
LOCAL_PATH = f"{REGIONS_NAME}"
REMOTE_FILE = f"~/{REGIONS_NAME}"

if os.path.exists(LOCAL_PATH):
    with open(LOCAL_PATH, 'w') as f:
        f.write(f"--- Truncated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    
TRUNCATE_CMD = f"ssh -o StrictHostKeyChecking=no -q -A saper-admin.svc.ad1.{REGIONS_NAME} '> {REMOTE_FILE}'"
subprocess.run(TRUNCATE_CMD, shell=True)

print("Fetching the data. Please wait...!⏳")
    
for ig in ["ig1", "ig2", "ig3"]:
    command = f"ssh -o StrictHostKeyChecking=no -q -A saper-admin.svc.ad1.{REGIONS_NAME} 'saper -r $(cat /etc/region) --ig {ig} vs ss list 2>/dev/null | jq -r \".[] | select(.status == \\\"LIVE\\\") | .hostName\"' >> {REGIONS_NAME}"
    try:
        process = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(process.stdout)
    except subprocess.CalledProcessError as e:
        print(f"\033[91mCommand execution failed on region {REGIONS_NAME}{e.stderr.strip()} Permission error, check and try again\033[0m")
        sys.exit(1)

print(f"{REGIONS_NAME} file copied successfully to your localhost✅\n")

FREE_BYTES_THRESHOLD = 2147483648
USED_PERCENT_THRESHOLD = 90
SERVERS_FILE = f"{REGIONS_NAME}"
SSH_OPTS = "-o GlobalKnownHostsFile=/dev/null -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -q"

with open(SERVERS_FILE, 'r') as f:
    servers = [line.strip() for line in f if line.strip() and not line.startswith("---")]

print(f"Total Storage Servers Count: {len(servers)}\n")

servers_to_clean = []

def check_server(server):
    cmd = f"ssh {SSH_OPTS} {server} \"df -B1 / | tail -1 | awk '{{print \\$4, \\$5}}'\""
    try:
        result = subprocess.run(cmd, shell=True, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.strip()
        parts = output.split()
        if len(parts) == 2:
            available_bytes = int(parts[0])
            used_percent = int(parts[1].strip('%'))
            available_gb = available_bytes / (1024 ** 3)
            print(f"{server} : Free space: {available_gb:.1f}GB, Used: {used_percent}%")
            if available_bytes <= FREE_BYTES_THRESHOLD or used_percent >= USED_PERCENT_THRESHOLD:
                return server 
    except subprocess.CalledProcessError as e:
        print(f"\033[91mError checking {server}: {e.stderr.strip()}\033[0m")
    return None

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(check_server, server): server for server in servers}

    for future in concurrent.futures.as_completed(futures):
        server = futures[future]
        try:
            result = future.result()
            if result:
                servers_to_clean.append(result)
        except Exception as exec:
            print(f"Error checking {server}: {exec}")

if not servers_to_clean:
    print("\n\033[92mDisk space is sufficient on all servers. No action required\033[0m")
    sys.exit(0)

print(f"\n{len(servers_to_clean)} Servers requiring cleanup, Please wait for cleaning up the space\n")

REMOTE_CMD = "sudo rm -rf /var/log/*; echo '---END-OF-LS---'; df -h / | tail -1 | awk '{print \\$4}'"
attention_servers = []

for server in servers_to_clean:
    try:
        cmd = (f"ssh {SSH_OPTS} {server} \"{REMOTE_CMD}\"")
        result = subprocess.run(cmd, check=True, shell=True, capture_output=True, text=True)
        output = result.stdout.strip()

        ls_output, df_output = output.split('---END-OF-LS---')

        print(ls_output.strip())  

        last_line = df_output.strip()
        if last_line.endswith("G"):
            free_gb = float(last_line.rstrip("G"))
            if free_gb < 2:
                print(f"\033[91m{server} needs attention: less than 2GB free after cleanup\033[0m")
                attention_servers.append(server)
            else:
                print(f"\033[92m{server} has sufficient space: {free_gb}G free\033[0m")
        else:
            print(f"{server} returned unexpected disk space format: '{last_line}'")
            attention_servers.append(server)

    except subprocess.CalledProcessError as e:
        print(f"Error executing listing on {server}")
        print(f"stderr: {e.stderr.strip() if e.stderr else 'No stderr'}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error on {server}: {str(e)}")
        sys.exit(1)

print("\n")

if not attention_servers:
    print("Cleanup successful. Sufficient disk space available on all nodes")
else:
    print("Tried Cleanup, but the following servers need attention (< 2GB free)")
    for k in attention_servers:
        print(f"\033[91m{k}\033[0m")
