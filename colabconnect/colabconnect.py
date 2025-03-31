from pathlib import Path
import subprocess
from importlib import import_module
import time
import sys
import os
import shutil


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


def create_proxychains_config(proxy_url="proxy.company.com", proxy_port=8080):
    """Create a custom proxychains.conf file for VSCode tunnel."""
    config_path = Path("proxychains_vscode.conf")
    
    config_content = f"""# proxychains.conf for VSCode tunnel
dynamic_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
# Corporate HTTP proxy
http {proxy_url} {proxy_port}
"""
    
    with open(config_path, "w") as f:
        f.write(config_content)
    
    print(f"Created custom proxychains configuration at {config_path.absolute()}")
    return config_path.absolute()


def start_tunnel(proxy_url=None, proxy_port=None) -> None:
    """Start the VSCode tunnel using proxychains-ng."""
    # Check if proxychains-ng is installed
    if not check_proxychains_installed():
        print("WARNING: proxychains-ng is not installed. Falling back to direct connection.")
        command = "./code tunnel --accept-server-license-terms --name colab-connect"
    else:
        # Create custom proxychains config
        config_path = create_proxychains_config(proxy_url, proxy_port)
        
        # Use proxychains-ng to start the tunnel
        command = f"proxychains4 -f {config_path} ./code tunnel --accept-server-license-terms --name colab-connect"
        print(f"Starting VSCode tunnel with proxychains-ng using config: {config_path}")
    
    p = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    show_outputs = False
    while True:
        line = p.stdout.readline().decode("utf-8")
        if show_outputs:
            print(line.strip())
        if "To grant access to the server" in line:
            print(line.strip())
        if "Open this link" in line:
            print("Starting the tunnel")
            time.sleep(5)
            print(message)
            print("Logs:")
            show_outputs = True
            line = ""
        if line == "" and p.poll() is not None:
            break
    return None


def run(command: str) -> None:
    process = subprocess.run(command.split())
    if process.returncode == 0:
        print(f"Ran: {command}")

def is_colab():
    return 'google.colab' in sys.modules

def colabconnect(proxy_url="proxy.company.com", proxy_port=8080) -> None:
    """
    Connect to VSCode tunnel through a corporate proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy (default: proxy.company.com)
        proxy_port (int): The port of the corporate proxy (default: 8080)
    """

    print("Installing python libraries...")
    run("pip3 install --user flake8 black ipywidgets twine")
    run("pip3 install -U ipykernel")
    run("apt install htop -y")

    # Proxy string for curl
    proxy_string = f"http://{proxy_url}:{proxy_port}"
    
    print("Installing vscode-cli...")
    run(
        f"curl -Lk --proxy '{proxy_string}' 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz"
    )
    run("tar -xf vscode_cli.tar.gz")

    print("Starting the tunnel")
    start_tunnel(proxy_url, proxy_port)
