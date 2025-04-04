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


def strip_protocol(url):
    """Strip protocol prefix from URL."""
    if url.startswith("http://"):
        return url[7:]
    elif url.startswith("https://"):
        return url[8:]
    return url


def resolve_hostname(hostname):
    """Resolve hostname to IP address."""
    # Strip protocol prefix if present
    hostname = strip_protocol(hostname)
    
    try:
        print(f"Resolving hostname: {hostname}")
        ip_address = socket.gethostbyname(hostname)
        print(f"Resolved {hostname} to {ip_address}")
        return ip_address
    except socket.gaierror as e:
        print(f"Failed to resolve hostname {hostname}: {str(e)}")
        return None


def create_proxychains_config(proxy_url="proxy.company.com", proxy_port=8080,
                             enable_proxy_dns=True):
    """
    Create a custom proxychains.conf file for VSCode tunnel.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        enable_proxy_dns (bool): Whether to enable proxy_dns in config

        
    Returns:
        Path: Path to the created config file
    """
    config_path = Path("proxychains_vscode.conf")
    
    
    
    # Original behavior - resolve hostname to IP
    clean_proxy_url = strip_protocol(proxy_url)
    proxy_ip = clean_proxy_url
    proxy_port_to_use = proxy_port
        
    if not all(c.isdigit() or c == '.' for c in clean_proxy_url):
        resolved_ip = resolve_hostname(clean_proxy_url)
        if resolved_ip:
            proxy_ip = resolved_ip
        else:
            print(f"WARNING: Could not resolve {clean_proxy_url} to an IP address. Proxychains requires numeric IPs.")
            print("Using the hostname anyway, but it will likely fail.")
    
    # Determine whether to include proxy_dns based on parameter
    dns_setting = "proxy_dns_old" if enable_proxy_dns else "# proxy_dns disabled"
    
    config_content = f"""# proxychains.conf for VSCode tunnel
dynamic_chain
{dns_setting}
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
# Corporate HTTP proxy
http {proxy_ip} {proxy_port_to_use} connect
"""
    
    with open(config_path, "w") as f:
        f.write(config_content)
    
    print(f"Created custom proxychains configuration at {config_path.absolute()}")
    return config_path.absolute()



    """
    Test if proxychains-ng is working correctly with the given proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        enable_proxy_dns (bool): Whether to enable proxy_dns in config
        
    Returns:
        bool: True if proxychains test was successful, False otherwise
    """
    print("Testing proxychains-ng with a simple command...")
    
    # Create proxychains config
    config_path = create_proxychains_config(
        proxy_url, proxy_port, enable_proxy_dns
    )
    
    # Try different test URLs in case one is blocked
    test_urls = [
        "https://github.com",
        "https://ifconfig.me",
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com"
    ]
    
    # Try each URL
    for test_url in test_urls:
        print(f"Testing proxychains with URL: {test_url}")
        test_command = f"proxychains4 -f {config_path} curl -s {test_url}"
        
        # Try up to 3 times with each URL
        for attempt in range(1, 4):
            try:
                print(f"Attempt {attempt} of 3...")
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
                    
            except subprocess.TimeoutExpired:
                print(f"Proxychains test timed out after 30 seconds on attempt {attempt}")
                if attempt < 3:
                    print(f"Waiting 2 seconds before retry...")
                    time.sleep(2)
            except Exception as e:
                print(f"Proxychains test failed with exception: {str(e)}")
                if attempt < 3:
                    print(f"Waiting 2 seconds before retry...")
                    time.sleep(2)
    
    # If we get here, all URLs and attempts failed
    print("All proxychains tests failed after multiple attempts with different URLs.")
    return False


def find_available_port():
    """
    Find an available port on the local machine.
    
    Returns:
        int: An available port number
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]   

def start_tunnel(proxy_url=None, proxy_port=None, enable_proxy_dns=True) -> None:
    """
    Start the VSCode tunnel using proxychains-ng.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy (usually 8080)
        enable_proxy_dns (bool): Whether to enable proxy_dns in config
    """
    use_proxychains=True
    # Check if proxychains-ng is installed
    if not check_proxychains_installed():
        print("WARNING: proxychains-ng is not installed. Falling back to direct connection.")
        use_proxychains = False
    
    # Prepare the command
    base_command = "./code tunnel --verbose --accept-server-license-terms --name colab-connect --log debug"
    
    if use_proxychains:
        config_path = create_proxychains_config(
            proxy_url, proxy_port, enable_proxy_dns
        )
        command = f"proxychains4 -f {config_path} {base_command}"
        print(f"Starting VSCode tunnel with proxychains-ng using config: {config_path}")
        if not enable_proxy_dns:
            print("Note: proxy_dns is disabled in proxychains configuration")
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
    command = "./code tunnel --accept-server-license-terms --verbose --name colab-connect --log debug"
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


def colabconnect(proxy_url="proxy.company.com", proxy_port=8080,
                enable_proxy_dns=True) -> None:
    """
    Connect to VSCode tunnel through a corporate proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy (default: proxy.company.com)
        proxy_port (int): The port of the corporate proxy (default: 8080)
        enable_proxy_dns (bool): Whether to enable proxy_dns in proxychains config (default: True)
    """

    print("Installing python libraries...")
    run("pip3 install --user flake8 black ipywidgets twine")
    run("pip3 install -U ipykernel")
    run("apt install htop -y")

    # Proxy string for curl
    # Check if proxy_url already includes a protocol prefix
    if proxy_url.startswith("http://") or proxy_url.startswith("https://"):
        proxy_string = f"{proxy_url}:{proxy_port}"
    else:
        proxy_string = f"http://{proxy_url}:{proxy_port}"
    
    print(f"Using proxy: {proxy_string}")
    
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
            direct_cmd = "curl -Lk https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64 --output vscode_cli.tar.gz"
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
            direct_cmd = "curl -Lk https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64 --output vscode_cli.tar.gz"
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
#            extract_result = subprocess.run("tar -xf vscode_cli.tar.gz", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            extract_result = subprocess.run("unzip vscode_cli.zip", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    
    # Strip protocol prefix for proxychains
    clean_proxy_url = strip_protocol(proxy_url)
    
    print("Starting the tunnel")
    start_tunnel(clean_proxy_url, proxy_port, enable_proxy_dns)
def test_github_dns_cli():
    """
    Command-line interface for testing GitHub DNS resolution.
    This function can be called directly to test DNS resolution without starting the tunnel.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Test GitHub DNS resolution')
    parser.add_argument('--system-hosts', action='store_true',
                        help='Update system hosts file (requires sudo)')
    parser.add_argument('--no-connection-test', action='store_true',
                        help='Skip connection test')
    parser.add_argument('--hosts-file', type=str, default='./github_hosts_test',
                        help='Path to hosts file (default: ./github_hosts_test)')
    
    args = parser.parse_args()
    
    # If system-hosts is specified, use /etc/hosts
    hosts_file_path = '/etc/hosts' if args.system_hosts else args.hosts_file
    use_sudo = args.system_hosts
    test_connection = not args.no_connection_test
    
    print(f"Testing GitHub DNS resolution with the following settings:")
    print(f"  Hosts file: {hosts_file_path}")
    print(f"  Use sudo: {use_sudo}")
    print(f"  Test connection: {test_connection}")
    
    # Resolve GitHub domains
    resolved_ips = resolve_github_domains()
    if not resolved_ips:
        print("Failed to resolve any GitHub domains")
        return 1
    
    # Add to hosts file
    if not add_to_hosts_file(resolved_ips, hosts_file_path, use_sudo):
        print("Failed to add GitHub domains to hosts file")
        return 1
    
    # Test connection if requested
    if test_connection:
        print("\nTesting connection to GitHub...")
        try:
            # Use curl to test connection to GitHub
            cmd = "curl -s -o /dev/null -w '%{http_code}' https://github.com"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            status_code = result.stdout.decode('utf-8').strip()
            
            if result.returncode == 0 and status_code.startswith('2'):
                print(f"✓ Successfully connected to GitHub (HTTP {status_code})")
                print("\nDNS resolution test successful!")
                return 0
            else:
                print(f"✗ Failed to connect to GitHub (HTTP {status_code})")
                print(f"Error: {result.stderr.decode('utf-8')}")
                print("\nDNS resolution test failed!")
                return 1
        except Exception as e:
            print(f"✗ Error testing connection to GitHub: {str(e)}")
            print("\nDNS resolution test failed!")
            return 1
    
    print("\nDNS resolution test completed successfully!")
    return 0


# If this script is run directly, handle command-line arguments
if __name__ == "__main__":
    import sys
    
    # Check if any arguments were provided
    if len(sys.argv) > 1:
        # If the first argument is "test_github_dns_cli", run the CLI
        if sys.argv[1] == "test_github_dns_cli":
            # Remove the first argument so argparse works correctly
            sys.argv.pop(1)
            sys.exit(test_github_dns_cli())
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("Available commands:")
            print("  test_github_dns_cli - Test GitHub DNS resolution")
            sys.exit(1)
    else:
        # If no arguments were provided, print usage information
        print("Usage: python -m colabconnect.colabconnect <command> [options]")
        print("Available commands:")
        print("  test_github_dns_cli - Test GitHub DNS resolution")
        print("\nFor help with a specific command, run:")
        print("  python -m colabconnect.colabconnect <command> --help")
        sys.exit(0)


def resolve_github_domains():
    """
    Resolve key GitHub domains to their IP addresses.
    
    Returns:
        dict: Dictionary mapping domain names to IP addresses
    """
    print("Resolving key GitHub domains...")
    
    # List of key GitHub domains needed for authentication
    github_domains = [
        "github.com",
        "api.github.com",
        "codeload.github.com",
        "raw.githubusercontent.com"
    ]
    
    # Dictionary to store resolved IPs
    resolved_ips = {}
    
    # Resolve each domain
    for domain in github_domains:
        print(f"Attempting to resolve {domain}...")
        ip = resolve_hostname(domain)
        if ip:
            resolved_ips[domain] = ip
            print(f"✓ Resolved {domain} to {ip}")
        else:
            print(f"✗ Failed to resolve {domain}")
    
    # Summary
    if resolved_ips:
        print(f"Successfully resolved {len(resolved_ips)}/{len(github_domains)} GitHub domains")
    else:
        print("Failed to resolve any GitHub domains")
    
    return resolved_ips


def add_to_hosts_file(resolved_ips, hosts_file_path="./github_hosts_test", use_sudo=False):
    """
    Add resolved GitHub domains to a hosts file.
    
    Args:
        resolved_ips (dict): Dictionary mapping domain names to IP addresses
        hosts_file_path (str): Path to hosts file (default: ./github_hosts_test)
        use_sudo (bool): Whether to use sudo when updating the hosts file (default: False)
        
    Returns:
        bool: True if hosts file was updated successfully, False otherwise
    """
    if not resolved_ips:
        print("No domains to add to hosts file")
        return False
    
    print(f"Adding {len(resolved_ips)} GitHub domains to hosts file: {hosts_file_path}")
    
    # Create hosts file entries
    hosts_entries = "\n# GitHub domains pre-resolved for VSCode tunnel testing\n"
    for domain, ip in resolved_ips.items():
        hosts_entries += f"{ip} {domain}\n"
    
    try:
        if use_sudo and hosts_file_path.startswith("/etc"):
            # Using sudo to append to the hosts file
            print(f"Updating hosts file at {hosts_file_path} with sudo...")
            
            # Write to a temporary file first
            temp_file = Path("github_hosts_entries.txt")
            with open(temp_file, "w") as f:
                f.write(hosts_entries)
            
            result = subprocess.run(
                ["sudo", "bash", "-c", f"cat {temp_file} >> {hosts_file_path}"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Clean up the temporary file
            temp_file.unlink()
        else:
            # Directly write to the hosts file
            print(f"Writing to hosts file at {hosts_file_path}...")
            with open(hosts_file_path, "w") as hosts_file:
                hosts_file.write(hosts_entries)
        
        print(f"Successfully added GitHub domains to hosts file: {hosts_file_path}")
        print("Hosts file entries:")
        print(hosts_entries)
        return True
    except Exception as e:
        print(f"Failed to update hosts file: {str(e)}")
        return False


