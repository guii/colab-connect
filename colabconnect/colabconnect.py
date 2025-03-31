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


def check_socat_installed():
    """Check if socat is installed and install it if not."""
    if shutil.which("socat"):
        print("socat is already installed")
        return True
    
    print("Installing socat...")
    try:
        subprocess.run(["apt-get", "update"], check=True)
        subprocess.run(["apt-get", "install", "-y", "socat"], check=True)
        
        if shutil.which("socat"):
            print("socat installed successfully")
            return True
        else:
            print("Failed to install socat")
            return False
    except Exception as e:
        print(f"Error installing socat: {str(e)}")
        return False
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
                             enable_proxy_dns=True, use_tls_tunnel=False,
                             local_port=24351):
    """
    Create a custom proxychains.conf file for VSCode tunnel.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        enable_proxy_dns (bool): Whether to enable proxy_dns in config
        use_tls_tunnel (bool): Whether to use local socat TLS tunnel
        local_port (int): The local port for socat tunnel
        
    Returns:
        Path: Path to the created config file
    """
    config_path = Path("proxychains_vscode.conf")
    
    # If using TLS tunnel, point to localhost with the local port
    if use_tls_tunnel:
        proxy_ip = "127.0.0.1"
        proxy_port_to_use = local_port
        print(f"Configuring proxychains to use local socat tunnel at {proxy_ip}:{proxy_port_to_use}")
    else:
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
    dns_setting = "proxy_dns" if enable_proxy_dns else "# proxy_dns disabled"
    
    config_content = f"""# proxychains.conf for VSCode tunnel
dynamic_chain
{dns_setting}
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
# Corporate HTTP proxy
http {proxy_ip} {proxy_port_to_use}
"""
    
    with open(config_path, "w") as f:
        f.write(config_content)
    
    print(f"Created custom proxychains configuration at {config_path.absolute()}")
    return config_path.absolute()


def test_proxychains(proxy_url, proxy_port, enable_proxy_dns=True, use_tls_tunnel=False, local_port=24351):
    """
    Test if proxychains-ng is working correctly with the given proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        enable_proxy_dns (bool): Whether to enable proxy_dns in config
        use_tls_tunnel (bool): Whether to use local socat TLS tunnel
        local_port (int): The local port for socat tunnel
        
    Returns:
        bool: True if proxychains test was successful, False otherwise
    """
    print("Testing proxychains-ng with a simple command...")
    
    # Create proxychains config
    config_path = create_proxychains_config(
        proxy_url, proxy_port, enable_proxy_dns, use_tls_tunnel, local_port
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
                    
                    # If using TLS tunnel, try a direct HTTP request to the tunnel to see if it's working
                    if use_tls_tunnel and attempt == 1:
                        print("Testing direct connection to socat tunnel...")
                        direct_test = f"curl -v --proxy http://127.0.0.1:{local_port} {test_url}"
                        try:
                            direct_result = subprocess.run(
                                direct_test,
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                timeout=10
                            )
                            if direct_result.returncode == 0:
                                print("Direct connection to socat tunnel works, but proxychains fails.")
                                print("This suggests an issue with proxychains configuration.")
                            else:
                                print("Direct connection to socat tunnel also fails.")
                                print("This suggests an issue with the socat tunnel itself.")
                        except Exception as e:
                            print(f"Error testing direct connection: {str(e)}")
                    
                    # Wait before retrying
                    if attempt < 3:
                        print(f"Waiting 2 seconds before retry...")
                        time.sleep(2)
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
    
    # If using TLS tunnel, provide additional debugging information
    if use_tls_tunnel:
        print("\nDebugging TLS tunnel:")
        print("1. Verify that your proxy supports TLS connections on the specified port")
        print("2. Check if your proxy requires authentication")
        print("3. Try using a different TLS port (default is 443)")
        print("4. Check if your proxy allows connections to the test URLs")
        
        # Try a simple HTTP request through the tunnel to see if it's working at all
        print("\nTesting basic HTTP connectivity through tunnel...")
        try:
            http_test = f"curl -v --proxy http://127.0.0.1:{local_port} http://example.com"
            http_result = subprocess.run(
                http_test,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10
            )
            if http_result.returncode == 0:
                print("Basic HTTP connectivity through tunnel works!")
                print("This suggests an issue with HTTPS/TLS connections specifically.")
            else:
                print("Basic HTTP connectivity through tunnel fails.")
                print("This suggests a fundamental issue with the tunnel configuration.")
        except Exception as e:
            print(f"Error testing HTTP connectivity: {str(e)}")
    
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

def start_socat_tunnel(proxy_url, proxy_port, local_port=None):
    """
    Start a socat tunnel that forwards traffic from a local port to the proxy over TLS.
    
    Args:
        proxy_url (str): The URL of the proxy server
        proxy_port (int): The port of the proxy server for TLS (usually 443)
        local_port (int): The local port to listen on (if None, an available port will be found)
        
    Returns:
        tuple: (subprocess.Popen, int) - The socat process and the local port, or (None, None) if failed
    """
    if not check_socat_installed():
        return None, None
    
    # Find an available port if not specified
    if local_port is None:
        local_port = find_available_port()
        print(f"Found available port: {local_port}")
    
    # Clean proxy URL (remove protocol prefix)
    clean_proxy_url = strip_protocol(proxy_url)
    original_hostname = clean_proxy_url
    
    # Resolve hostname to IP if it's not already an IP
    proxy_ip = clean_proxy_url
    if not all(c.isdigit() or c == '.' for c in clean_proxy_url):
        resolved_ip = resolve_hostname(clean_proxy_url)
        if resolved_ip:
            proxy_ip = resolved_ip
    
    # Try a different approach using HTTP PROXY mode instead of direct TLS
    # This uses the HTTP CONNECT method which is what proxychains is trying to do anyway
    # This might work better with corporate proxies that don't allow direct TLS connections
    print("Using HTTP PROXY mode with socat instead of direct TLS connection")
    
    # First, try the HTTP PROXY approach
    cmd = (
        f"socat -v TCP-LISTEN:{local_port},bind=127.0.0.1,fork,reuseaddr,nodelay "
        f"PROXY:{proxy_ip}:{proxy_port}:github.com:443,proxyport={proxy_port},resolve"
    )
    print(f"Starting socat tunnel (attempt 1 - HTTP PROXY mode): {cmd}")
    
    # Try multiple approaches in sequence until one works
    for attempt in range(1, 4):
        try:
            # Start socat in the background
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Give it a moment to start
            time.sleep(2)
            
            # Check if process is still running
            if process.poll() is None:
                print(f"Socat tunnel started successfully on 127.0.0.1:{local_port}")
                
                # Test the tunnel directly
                print("Testing socat tunnel with a direct connection to github.com...")
                test_cmd = f"curl -v --proxy http://127.0.0.1:{local_port} https://github.com"
                try:
                    test_result = subprocess.run(
                        test_cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=10
                    )
                    
                    if test_result.returncode == 0:
                        print(f"Socat tunnel test successful! Response: {test_result.stdout.decode('utf-8').strip()}")
                        return process, local_port
                    else:
                        print(f"Socat tunnel test failed with return code {test_result.returncode}")
                        print(f"Error output: {test_result.stderr.decode('utf-8')}")
                        
                        # If this is the last attempt, return the process anyway
                        if attempt == 3:
                            print("All socat tunnel approaches failed, but returning the last one anyway.")
                            return process, local_port
                        
                        # Otherwise, terminate this process and try the next approach
                        process.terminate()
                        time.sleep(1)
                except Exception as e:
                    print(f"Error testing socat tunnel: {str(e)}")
                    
                    # If this is the last attempt, return the process anyway
                    if attempt == 3:
                        print("All socat tunnel approaches failed, but returning the last one anyway.")
                        return process, local_port
                    
                    # Otherwise, terminate this process and try the next approach
                    process.terminate()
                    time.sleep(1)
            else:
                stdout, stderr = process.communicate()
                print(f"Socat failed to start: {stderr}")
                
                # If this is the last attempt, return None
                if attempt == 3:
                    print("All socat tunnel approaches failed.")
                    return None, None
            
            # Try a different approach for the next attempt
            if attempt == 1:
                # Second attempt: Try direct TCP connection (no TLS)
                print("\nTrying alternative approach (attempt 2 - direct TCP)...")
                cmd = (
                    f"socat -v TCP-LISTEN:{local_port},bind=127.0.0.1,fork,reuseaddr "
                    f"TCP:{proxy_ip}:{proxy_port}"
                )
                print(f"Starting socat tunnel (attempt 2 - direct TCP): {cmd}")
            elif attempt == 2:
                # Third attempt: Try original OPENSSL approach
                print("\nTrying alternative approach (attempt 3 - OPENSSL)...")
                cmd = (
                    f"socat -v TCP-LISTEN:{local_port},bind=127.0.0.1,fork,reuseaddr,nodelay "
                    f"OPENSSL:{proxy_ip}:{proxy_port},verify=0,method=TLSv1.2,sni-hostname={original_hostname},"
                    f"alpn=http/1.1,cipher=HIGH:!aNULL:!eNULL:!EXPORT:!DES:!MD5:!PSK:!RC4,"
                    f"ignoreeof=1,nodelay=1,connect-timeout=10"
                )
                print(f"Starting socat tunnel (attempt 3 - OPENSSL): {cmd}")
        except Exception as e:
            print(f"Error starting socat (attempt {attempt}): {str(e)}")
            
            # If this is the last attempt, return None
            if attempt == 3:
                print("All socat tunnel approaches failed.")
                return None, None
    
    # If we get here, all attempts failed
    return None, None

def start_tunnel(proxy_url=None, proxy_port=None, enable_proxy_dns=True, use_tls_tunnel=False,
                tls_port=443, force_tls_tunnel=False) -> None:
    """
    Start the VSCode tunnel using proxychains-ng.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy (usually 8080)
        enable_proxy_dns (bool): Whether to enable proxy_dns in config
        use_tls_tunnel (bool): Whether to use socat TLS tunnel
        tls_port (int): The port to use for TLS connection to proxy (usually 443)
        force_tls_tunnel (bool): Whether to force using the TLS tunnel even if tests fail
    """
    # Check if proxychains-ng is installed
    if not check_proxychains_installed():
        print("WARNING: proxychains-ng is not installed. Falling back to direct connection.")
        use_proxychains = False
        socat_process = None
    else:
        # Start socat TLS tunnel if requested
        socat_process = None
        local_port = None  # Will be determined dynamically
        
        if use_tls_tunnel:
            print("Setting up TLS tunnel with socat...")
            socat_process, local_port = start_socat_tunnel(proxy_url, tls_port, local_port)
            if not socat_process:
                print("WARNING: Failed to start socat TLS tunnel. Falling back to direct proxy.")
                use_tls_tunnel = False
                local_port = None
        
        # Test if proxychains is working with the given proxy
        use_proxychains = test_proxychains(proxy_url, proxy_port, enable_proxy_dns, use_tls_tunnel, local_port)
        
        # If proxychains test failed but force_tls_tunnel is enabled, continue using the tunnel anyway
        if not use_proxychains:
            if force_tls_tunnel and socat_process and use_tls_tunnel:
                print("WARNING: proxychains-ng test failed, but force_tls_tunnel is enabled.")
                print("Continuing with TLS tunnel despite test failure...")
                use_proxychains = True
            else:
                print("WARNING: proxychains-ng test failed. Falling back to direct connection.")
                # Kill socat process if it was started
                if socat_process:
                    socat_process.terminate()
                    socat_process = None
    
    # Prepare the command
    base_command = "./code tunnel --verbose --accept-server-license-terms --name colab-connect --log debug"
    
    if use_proxychains:
        config_path = create_proxychains_config(
            proxy_url, proxy_port, enable_proxy_dns, use_tls_tunnel, local_port
        )
        command = f"proxychains4 -f {config_path} {base_command}"
        print(f"Starting VSCode tunnel with proxychains-ng using config: {config_path}")
        if not enable_proxy_dns:
            print("Note: proxy_dns is disabled in proxychains configuration")
        if use_tls_tunnel:
            print("Note: Using socat TLS tunnel for secure proxy connection")
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
    
    # Terminate socat process if it was started
    if socat_process:
        print("Terminating socat TLS tunnel...")
        socat_process.terminate()
    
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
                enable_proxy_dns=True, test_github_dns_resolution=False,
                use_system_hosts=False, use_tls_tunnel=False, tls_port=443,
                force_tls_tunnel=False) -> None:
    """
    Connect to VSCode tunnel through a corporate proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy (default: proxy.company.com)
        proxy_port (int): The port of the corporate proxy (default: 8080)
        enable_proxy_dns (bool): Whether to enable proxy_dns in proxychains config (default: True)
        test_github_dns_resolution (bool): Whether to test GitHub DNS resolution (default: False)
        use_system_hosts (bool): Whether to update the system hosts file (default: False)
        use_tls_tunnel (bool): Whether to use socat to create a TLS tunnel to the proxy (default: False)
        tls_port (int): The port to use for TLS connection to proxy (default: 443)
        force_tls_tunnel (bool): Whether to force using the TLS tunnel even if tests fail (default: False)
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
    
    # Test GitHub DNS resolution if requested
    if test_github_dns_resolution:
        print("Testing GitHub DNS resolution before starting tunnel...")
        test_github_dns(use_system_hosts)
    
    # Strip protocol prefix for proxychains
    clean_proxy_url = strip_protocol(proxy_url)
    
    print("Starting the tunnel")
    start_tunnel(clean_proxy_url, proxy_port, enable_proxy_dns, use_tls_tunnel, tls_port, force_tls_tunnel)
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


def test_github_dns(use_system_hosts=False, test_connection=True):
    """
    Test GitHub DNS resolution by resolving domains and optionally adding them to hosts file.
    
    Args:
        use_system_hosts (bool): Whether to update the system hosts file (default: False)
        test_connection (bool): Whether to test connection to GitHub (default: True)
        
    Returns:
        bool: True if test was successful, False otherwise
    """
    print("Testing GitHub DNS resolution...")
    
    # Resolve GitHub domains
    resolved_ips = resolve_github_domains()
    if not resolved_ips:
        return False
    
    # Add to hosts file
    hosts_file_path = "/etc/hosts" if use_system_hosts else "./github_hosts_test"
    use_sudo = use_system_hosts
    
    if not add_to_hosts_file(resolved_ips, hosts_file_path, use_sudo):
        return False
    
    # Test connection to GitHub if requested
    if test_connection:
        print("Testing connection to GitHub...")
        try:
            # Use curl to test connection to GitHub
            cmd = "curl -s -o /dev/null -w '%{http_code}' https://github.com"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            status_code = result.stdout.decode('utf-8').strip()
            
            if result.returncode == 0 and status_code.startswith('2'):
                print(f"✓ Successfully connected to GitHub (HTTP {status_code})")
                return True
            else:
                print(f"✗ Failed to connect to GitHub (HTTP {status_code})")
                print(f"Error: {result.stderr.decode('utf-8')}")
                return False
        except Exception as e:
            print(f"✗ Error testing connection to GitHub: {str(e)}")
            return False
    
    return True

