from pathlib import Path
import subprocess
from importlib import import_module
import time
import sys
import os
import shutil
import socket


message = """
- Ready!
- Open VSCode on your laptop and open the command prompt
- Select: 'Remote-Tunnels: Connect to Tunnel' to connect to colab
""".strip()


def check_proxychains_installed():
    """Check if proxychains-ng is installed and install it if not."""
    if shutil.which("proxychains4"):
        print("proxychains-ng is already installed")
        return True
    
    print("Installing proxychains-ng...")
    # Clone the repository if not already present
    if not Path("proxychains-ng").exists():
        subprocess.run(["git", "clone", "https://github.com/rofl0r/proxychains-ng.git"], check=True)
    
    # Build and install proxychains-ng
    os.chdir("proxychains-ng")
    subprocess.run(["./configure", "--prefix=/usr", "--sysconfdir=/etc"], check=True)
    subprocess.run(["make"], check=True)
    subprocess.run(["make", "install"], check=True)
    os.chdir("..")
    
    if shutil.which("proxychains4"):
        print("proxychains-ng installed successfully")
        return True
    else:
        print("Failed to install proxychains-ng")
        return False


def resolve_hostname(hostname):
    """Resolve hostname to IP address."""
    try:
        print(f"Resolving hostname: {hostname}")
        ip_address = socket.gethostbyname(hostname)
        print(f"Resolved {hostname} to {ip_address}")
        return ip_address
    except socket.gaierror as e:
        print(f"Failed to resolve hostname {hostname}: {str(e)}")
        return None


def create_proxychains_config(proxy_url="proxy.company.com", proxy_port=8080):
    """Create a custom proxychains.conf file for VSCode tunnel."""
    config_path = Path("proxychains_vscode.conf")
    
    # Resolve hostname to IP address if it's not already an IP
    proxy_ip = proxy_url
    if not all(c.isdigit() or c == '.' for c in proxy_url):
        resolved_ip = resolve_hostname(proxy_url)
        if resolved_ip:
            proxy_ip = resolved_ip
        else:
            print(f"WARNING: Could not resolve {proxy_url} to an IP address. Proxychains requires numeric IPs.")
            print("Using the hostname anyway, but it will likely fail.")
    
    config_content = f"""# proxychains.conf for VSCode tunnel
dynamic_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
# Corporate HTTP proxy
http {proxy_ip} {proxy_port}
"""
    
    with open(config_path, "w") as f:
        f.write(config_content)
    
    print(f"Created custom proxychains configuration at {config_path.absolute()}")
    return config_path.absolute()


def test_proxychains(proxy_url, proxy_port):
    """Test if proxychains-ng is working correctly with the given proxy."""
    print("Testing proxychains-ng with a simple command...")
    config_path = create_proxychains_config(proxy_url, proxy_port)
    test_command = f"proxychains4 -f {config_path} curl -s https://ifconfig.me"
    
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"Proxychains test successful! External IP: {result.stdout.decode('utf-8').strip()}")
            return True
        else:
            print(f"Proxychains test failed with return code {result.returncode}")
            print(f"Error output: {result.stderr.decode('utf-8')}")
            return False
    except subprocess.TimeoutExpired:
        print("Proxychains test timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"Proxychains test failed with exception: {str(e)}")
        return False


def start_tunnel(proxy_url=None, proxy_port=None) -> None:
    """Start the VSCode tunnel using proxychains-ng."""
    # Check if proxychains-ng is installed
    if not check_proxychains_installed():
        print("WARNING: proxychains-ng is not installed. Falling back to direct connection.")
        use_proxychains = False
    else:
        # Test if proxychains is working with the given proxy
        use_proxychains = test_proxychains(proxy_url, proxy_port)
        if not use_proxychains:
            print("WARNING: proxychains-ng test failed. Falling back to direct connection.")
    
    # Prepare the command
    base_command = "./code tunnel --accept-server-license-terms --name colab-connect"
    
    if use_proxychains:
        config_path = create_proxychains_config(proxy_url, proxy_port)
        command = f"proxychains4 -f {config_path} {base_command}"
        print(f"Starting VSCode tunnel with proxychains-ng using config: {config_path}")
    else:
        command = base_command
        print("Starting VSCode tunnel directly (without proxychains-ng)")
    
    # Start the process with both stdout and stderr captured
    print(f"Executing command: {command}")
    p = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    
    # Use separate threads to read stdout and stderr to avoid blocking
    from threading import Thread
    
    def read_output(pipe, prefix):
        for line in iter(pipe.readline, ''):
            print(f"{prefix}: {line.strip()}")
            if "To grant access to the server" in line:
                print(f"IMPORTANT: {line.strip()}")
            if "Open this link" in line:
                print("Tunnel is starting...")
                time.sleep(5)
                print(message)
    
    # Start threads to read output
    Thread(target=read_output, args=(p.stdout, "STDOUT")).start()
    Thread(target=read_output, args=(p.stderr, "STDERR")).start()
    
    # Wait for the process to complete
    p.wait()
    
    # Check the return code
    if p.returncode != 0:
        print(f"WARNING: VSCode tunnel process exited with code {p.returncode}")
        
        # If proxychains failed, try direct connection
        if use_proxychains:
            print("Attempting to start tunnel directly as fallback...")
            start_tunnel_direct()
    
    return None


def start_tunnel_direct():
    """Start the VSCode tunnel directly without proxychains-ng."""
    command = "./code tunnel --accept-server-license-terms --name colab-connect"
    print(f"Starting VSCode tunnel directly: {command}")
    
    p = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    
    # Use separate threads to read stdout and stderr to avoid blocking
    from threading import Thread
    
    def read_output(pipe, prefix):
        for line in iter(pipe.readline, ''):
            print(f"{prefix}: {line.strip()}")
            if "To grant access to the server" in line:
                print(f"IMPORTANT: {line.strip()}")
            if "Open this link" in line:
                print("Tunnel is starting...")
                time.sleep(5)
                print(message)
    
    # Start threads to read output
    Thread(target=read_output, args=(p.stdout, "STDOUT")).start()
    Thread(target=read_output, args=(p.stderr, "STDERR")).start()
    
    # Wait for the process to complete
    p.wait()
    
    return None


def run(command: str) -> None:
    process = subprocess.run(command.split())
    if process.returncode == 0:
        print(f"Ran: {command}")



def verify_vscode_cli():
    """Verify that the VSCode CLI is properly downloaded and extracted."""
    if os.path.exists("./code"):
        print("VSCode CLI found at ./code")
        # Make sure it's executable
        os.chmod("./code", 0o755)
        return True
    else:
        print("VSCode CLI not found at ./code")
        # Check if it's in the current directory with a different name
        code_files = list(Path(".").glob("code*"))
        if code_files:
            print(f"Found potential VSCode CLI files: {code_files}")
            for file in code_files:
                if os.path.isfile(file) and os.access(file, os.X_OK):
                    print(f"Found executable VSCode CLI at {file}")
                    # Create a symlink to ./code
                    os.symlink(file, "./code")
                    return True
        return False


def colabconnect(proxy_url="proxy.company.com", proxy_port=8080) -> None:
    """
    Connect to VSCode tunnel through a corporate proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy (default: proxy.company.com)
        proxy_port (int): The port of the corporate proxy (default: 8080)
    """
    if is_colab():
        print("Mounting Google Drive...")
        drive = import_module("google.colab.drive")
        drive.mount("/content/drive")
    
        # Create a folder on drive to store all the code files
        drive_folder = '/content/drive/MyDrive/colab/'
        Path(drive_folder).mkdir(parents=True, exist_ok=True)
    
        # Make a /colab path to easily access the folder
        run(f'ln -s {drive_folder} /')

    print("Installing python libraries...")
    run("pip3 install --user flake8 black ipywidgets twine")
    run("pip3 install -U ipykernel")
    run("apt install htop -y")

    # Proxy string for curl
    proxy_string = f"http://{proxy_url}:{proxy_port}"
    
    print("Installing vscode-cli...")
    vscode_cli_downloaded = False
    
    try:
        # Try with proxy first
        print(f"Downloading VSCode CLI using proxy: {proxy_string}")
        curl_cmd = f"curl -Lk --proxy '{proxy_string}' 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz"
        result = subprocess.run(curl_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            print(f"Proxy download failed: {result.stderr.decode('utf-8')}")
            print("Trying direct download...")
            direct_cmd = "curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz"
            direct_result = subprocess.run(direct_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if direct_result.returncode == 0:
                print("Direct download successful")
                vscode_cli_downloaded = True
            else:
                print(f"Direct download failed: {direct_result.stderr.decode('utf-8')}")
        else:
            print("Proxy download successful")
            vscode_cli_downloaded = True
    except Exception as e:
        print(f"Error during download: {str(e)}")
        print("Trying direct download...")
        try:
            direct_cmd = "curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz"
            direct_result = subprocess.run(direct_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if direct_result.returncode == 0:
                print("Direct download successful")
                vscode_cli_downloaded = True
            else:
                print(f"Direct download failed: {direct_result.stderr.decode('utf-8')}")
        except Exception as e2:
            print(f"Error during direct download: {str(e2)}")
    
    if vscode_cli_downloaded:
        print("Extracting VSCode CLI...")
        try:
            extract_result = subprocess.run("tar -xf vscode_cli.tar.gz", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if extract_result.returncode != 0:
                print(f"Extraction failed: {extract_result.stderr.decode('utf-8')}")
            else:
                print("Extraction successful")
        except Exception as e:
            print(f"Error during extraction: {str(e)}")
    
    # Verify VSCode CLI is available
    if not verify_vscode_cli():
        print("ERROR: VSCode CLI not found. Cannot start tunnel.")
        return
    
    print("Starting the tunnel")
    start_tunnel(proxy_url, proxy_port)
