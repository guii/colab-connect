from pathlib import Path
import subprocess
from importlib import import_module
import time
import sys
import os
import shutil
import socket
import tempfile
import ssl
import threading
import select
from http.server import HTTPServer, BaseHTTPRequestHandler
import http.client
import urllib.parse


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


def check_proxytunnel_installed():
    """Check if proxytunnel is installed and install it if not."""
    if shutil.which("proxytunnel"):
        print("proxytunnel is already installed")
        return True
    
    # Check if ./proxytunnel exists in current directory
    if os.path.exists("./proxytunnel") and os.path.isfile("./proxytunnel"):
        print("proxytunnel binary found in current directory")
        # Make sure it's executable
        os.chmod("./proxytunnel", 0o755)
        return True
    
    print("Installing proxytunnel using apt...")
    try:
        # Install proxytunnel using apt
        subprocess.run(["apt", "install", "-y", "proxytunnel"], check=True)
        
        if shutil.which("proxytunnel"):
            print("proxytunnel installed successfully via apt")
            return True
        else:
            print("Failed to install proxytunnel via apt")
            return False
    except Exception as e:
        print(f"Error installing proxytunnel via apt: {str(e)}")
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


def create_ssl_unverified_context():
    """Create an SSL context that doesn't verify certificates."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler that forwards requests to a target server through a proxy."""
    
    def __init__(self, *args, proxy_url=None, proxy_port=None, **kwargs):
        self.proxy_url = proxy_url
        self.proxy_port = proxy_port
        super().__init__(*args, **kwargs)
    
    def do_CONNECT(self):
        """Handle CONNECT requests (for HTTPS connections)."""
        # Parse the target address from the request
        host, port = self.path.split(':')
        port = int(port)
        
        print(f"CONNECT request for {host}:{port}")
        
        try:
            # Create a direct connection to the target
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(10)
            
            # Connect directly to the target (bypassing the proxy)
            print(f"Connecting directly to {host}:{port}")
            target_socket.connect((host, port))
            
            # Send a 200 response to the client
            self.send_response(200, 'Connection Established')
            self.send_header('Proxy-Agent', 'VSCode-Tunnel-Helper')
            self.end_headers()
            
            # Get the client socket
            client_socket = self.connection
            
            # Forward data between the client and the target
            self._forward_data(client_socket, target_socket)
        except Exception as e:
            print(f"Error in CONNECT: {str(e)}")
            self.send_error(502, f"Bad Gateway: {str(e)}")
    
    def _forward_data(self, client_socket, target_socket):
        """Forward data between the client and the target."""
        if not client_socket or not target_socket:
            print("Error: Invalid sockets for forwarding")
            return
            
        try:
            # Set sockets to non-blocking mode
            client_socket.setblocking(0)
            target_socket.setblocking(0)
            
            # Set timeout
            timeout = 1
            
            # Forward data until one of the sockets is closed
            while True:
                # Wait for data from either socket
                inputs = [client_socket, target_socket]
                try:
                    readable, _, exceptional = select.select(inputs, [], inputs, timeout)
                except select.error as e:
                    print(f"Select error: {str(e)}")
                    break
                
                # If there was an error with a socket, close both
                if exceptional:
                    print("Socket exception")
                    break
                
                # Read from client socket
                if client_socket in readable:
                    try:
                        data = client_socket.recv(4096)
                        if not data:
                            print("Client closed connection")
                            break
                        target_socket.sendall(data)
                    except Exception as e:
                        print(f"Error reading from client: {str(e)}")
                        break
                
                # Read from target socket
                if target_socket in readable:
                    try:
                        data = target_socket.recv(4096)
                        if not data:
                            print("Target closed connection")
                            break
                        client_socket.sendall(data)
                    except Exception as e:
                        print(f"Error reading from target: {str(e)}")
                        break
        except Exception as e:
            print(f"Error in data forwarding: {str(e)}")
        finally:
            # Close both sockets
            print("Closing connections")
            try:
                client_socket.close()
            except:
                pass
            try:
                target_socket.close()
            except:
                pass
        
    
    def do_GET(self):
        """Handle GET requests."""
        self._handle_request('GET')
    
    def do_POST(self):
        """Handle POST requests."""
        self._handle_request('POST')
    
    def do_PUT(self):
        """Handle PUT requests."""
        self._handle_request('PUT')
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        self._handle_request('DELETE')
    
    def do_HEAD(self):
        """Handle HEAD requests."""
        self._handle_request('HEAD')
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests."""
        self._handle_request('OPTIONS')
    
    def do_PATCH(self):
        """Handle PATCH requests."""
        self._handle_request('PATCH')
    
    def _handle_request(self, method):
        """Handle HTTP requests by forwarding them to the target through the proxy."""
        # Parse the URL
        url = urllib.parse.urlparse(self.path)
        
        # Read the request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None
        
        # Create a connection to the proxy
        proxy_conn = http.client.HTTPConnection(self.proxy_url, self.proxy_port)
        
        # Prepare headers for the proxy
        headers = dict(self.headers)
        
        # Send the request to the proxy
        proxy_conn.request(method, self.path, body=body, headers=headers)
        
        # Get the response from the proxy
        proxy_response = proxy_conn.getresponse()
        
        # Forward the response to the client
        self.send_response(proxy_response.status, proxy_response.reason)
        for header, value in proxy_response.getheaders():
            self.send_header(header, value)
        self.end_headers()
        
        # Forward the response body
        self.wfile.write(proxy_response.read())
        
        # Close the proxy connection
        proxy_conn.close()


def start_proxy_server(proxy_url, proxy_port, bind_port=0):
    """
    Start a local proxy server that forwards requests to the corporate proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        bind_port (int): The port to bind the local proxy server to (0 for auto-assign)
        
    Returns:
        tuple: (server, port) - The server object and the port it's listening on
    """
    # Create a request handler class with the proxy information
    handler = lambda *args, **kwargs: ProxyHTTPRequestHandler(*args, proxy_url=proxy_url, proxy_port=proxy_port, **kwargs)
    
    # Create the server
    server = HTTPServer(('127.0.0.1', bind_port), handler)
    
    # Get the port the server is listening on
    port = server.server_port
    
    # Start the server in a separate thread
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    
    print(f"Started local proxy server on port {port}")
    
    return server, port


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



def test_proxychains(proxy_url, proxy_port, enable_proxy_dns=True):
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
def start_tunnel_with_proxytunnel(proxy_url=None, proxy_port=None, proxy_user=None, proxy_pass=None,
                                use_ntlm=False, use_ssl=False) -> None:
    """
    Start the VSCode tunnel using Proxytunnel.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        proxy_user (str): Username for proxy authentication
        proxy_pass (str): Password for proxy authentication
        use_ntlm (bool): Whether to use NTLM authentication
        use_ssl (bool): Whether to use SSL to connect to the proxy
    """
    use_proxytunnel = True
    proxytunnel_process = None
    
    # Check if proxytunnel is installed
    if not check_proxytunnel_installed():
        print("WARNING: proxytunnel could not be installed. Falling back to direct connection.")
        use_proxytunnel = False
    
    # Verify VSCode CLI is available
    if not os.path.exists("./code"):
        print("ERROR: VSCode CLI not found at ./code. Make sure it's properly installed.")
        if not verify_vscode_cli():
            print("ERROR: Could not find or verify VSCode CLI. Cannot start tunnel.")
            return None
    
    # Prepare the command
    base_command = "NODE_TLS_REJECT_UNAUTHORIZED=0 ./code tunnel --verbose --accept-server-license-terms --name colab-connect --log debug"
    
    try:
        if use_proxytunnel:
            # Configure and start proxytunnel
            if proxy_user and proxy_pass:
                print(f"Configuring Proxytunnel with authentication (user: {proxy_user}, NTLM: {use_ntlm}, SSL: {use_ssl})")
                config = configure_proxytunnel_advanced(
                    proxy_url, proxy_port, proxy_user=proxy_user, proxy_pass=proxy_pass,
                    use_ntlm=use_ntlm, use_ssl=use_ssl
                )
            else:
                print(f"Configuring Proxytunnel without authentication")
                config = configure_proxytunnel(proxy_url, proxy_port)
                
            proxytunnel_process = start_proxytunnel(config)
            
            if proxytunnel_process:
                # Set environment variables for the VSCode tunnel to use the local proxy
                env = os.environ.copy()
                env["HTTPS_PROXY"] = f"http://localhost:{config['local_port']}"
                env["HTTP_PROXY"] = f"http://localhost:{config['local_port']}"
                env["http_proxy"] = f"http://localhost:{config['local_port']}"
                env["https_proxy"] = f"http://localhost:{config['local_port']}"
                # Disable SSL verification for all processes
                env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
                env["CURL_CA_BUNDLE"] = ""  # Empty to disable curl certificate verification
                env["SSL_CERT_FILE"] = ""    # Empty to disable Python SSL certificate verification
                env["GIT_SSL_NO_VERIFY"] = "1"  # For git operations
                env["npm_config_strict_ssl"] = "false"  # For npm
                env["SSL_CERT_FILE"] = ""    # Empty to disable Python SSL certificate verification
                
                print(f"Starting VSCode tunnel with Proxytunnel using local port {config['local_port']}")
                command = base_command
            else:
                print("Proxytunnel failed to start. Falling back to direct connection.")
                use_proxytunnel = False
                env = os.environ.copy()
                # Disable SSL verification
                env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
                env["CURL_CA_BUNDLE"] = ""
                env["SSL_CERT_FILE"] = ""
                env["GIT_SSL_NO_VERIFY"] = "1"
                env["npm_config_strict_ssl"] = "false"
        else:
            command = base_command
            print("Starting VSCode tunnel directly (without Proxytunnel)")
            env = os.environ.copy()
            # Disable SSL verification
            env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
            env["CURL_CA_BUNDLE"] = ""
            env["SSL_CERT_FILE"] = ""
            env["GIT_SSL_NO_VERIFY"] = "1"
            env["npm_config_strict_ssl"] = "false"
        
        # Start the process with both stdout and stderr captured
        print(f"Executing command: {command}")
        
        # Ensure SSL verification is disabled in the environment
        if 'NODE_TLS_REJECT_UNAUTHORIZED' not in env:
            env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
        if 'CURL_CA_BUNDLE' not in env:
            env["CURL_CA_BUNDLE"] = ""
        if 'SSL_CERT_FILE' not in env:
            env["SSL_CERT_FILE"] = ""
        
        p = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env
        )
        
        # Use separate threads to read stdout and stderr to avoid blocking
        from threading import Thread
        
        def read_output(pipe, prefix):
            try:
                for line in iter(pipe.readline, ''):
                    print(f"{prefix}: {line.strip()}")
                    if "To grant access to the server" in line:
                        print(f"IMPORTANT: {line.strip()}")
                    if "Open this link" in line:
                        print("Tunnel is starting...")
                        time.sleep(5)
                        print(message)
                    # Look for specific error messages
                    if "error" in line.lower() or "failed" in line.lower():
                        print(f"TUNNEL ERROR: {line.strip()}")
                    if "proxy" in line.lower() and ("error" in line.lower() or "failed" in line.lower()):
                        print(f"PROXY ERROR: {line.strip()}")
            except Exception as e:
                print(f"Error reading from {prefix}: {str(e)}")
        
        # Start threads to read output
        Thread(target=read_output, args=(p.stdout, "STDOUT")).start()
        Thread(target=read_output, args=(p.stderr, "STDERR")).start()
        
        # Wait for the process to complete
        p.wait()
        
        # Clean up the proxytunnel process if it was started
        if use_proxytunnel and proxytunnel_process:
            try:
                proxytunnel_process.terminate()
                print("Terminated Proxytunnel process")
            except Exception as e:
                print(f"Error terminating Proxytunnel process: {str(e)}")
        
        # Check the return code
        if p.returncode != 0:
            print(f"WARNING: VSCode tunnel process exited with code {p.returncode}")
            
            # If proxytunnel failed, try direct connection
            if use_proxytunnel:
                print("Attempting to start tunnel directly as fallback...")
                start_tunnel_direct()
        
        return None
    except Exception as e:
        print(f"ERROR: Failed to start VSCode tunnel: {str(e)}")
        
        # Clean up the proxytunnel process if it was started
        if use_proxytunnel and proxytunnel_process:
            try:
                proxytunnel_process.terminate()
                print("Terminated Proxytunnel process")
            except Exception as e2:
                print(f"Error terminating Proxytunnel process: {str(e2)}")
        
        return None


def start_tunnel_with_fallbacks(proxy_url, proxy_port, proxy_user=None, proxy_pass=None,
                              use_ntlm=False, use_ssl=False):
    """
    Start the VSCode tunnel with multiple fallback mechanisms.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        proxy_user (str): Username for proxy authentication
        proxy_pass (str): Password for proxy authentication
        use_ntlm (bool): Whether to use NTLM authentication
        use_ssl (bool): Whether to use SSL to connect to the proxy
    """
    # Try Proxytunnel first
    if check_proxytunnel_installed():
        # Try different target configurations
        targets = [
            {"host": "vscode.dev", "port": 443},
            {"host": "global.rel.tunnels.api.visualstudio.com", "port": 443},
            {"host": "online.visualstudio.com", "port": 443}
        ]
        
        for target in targets:
            print(f"Trying Proxytunnel with target {target['host']}:{target['port']}")
            
            if proxy_user and proxy_pass:
                config = configure_proxytunnel_advanced(
                    proxy_url, proxy_port, target["host"], target["port"],
                    proxy_user=proxy_user, proxy_pass=proxy_pass,
                    use_ntlm=use_ntlm, use_ssl=use_ssl
                )
            else:
                config = configure_proxytunnel(proxy_url, proxy_port, target["host"], target["port"])
                
            # Test the connection first
            if test_proxytunnel_connection(config):
                print(f"Proxytunnel connection test successful with target {target['host']}:{target['port']}")
                
                # Start the tunnel with this configuration
                start_tunnel_with_proxytunnel(
                    proxy_url, proxy_port, proxy_user, proxy_pass, use_ntlm, use_ssl
                )
                return
            else:
                print(f"Proxytunnel connection test failed with target {target['host']}:{target['port']}")
        
        print("All Proxytunnel configurations failed")
    
    # Try proxychains-ng as fallback
    print("Trying proxychains-ng as fallback")
    if check_proxychains_installed():
        start_tunnel(proxy_url, proxy_port, enable_proxy_dns=False)
        return
    
    # Try direct connection as last resort
    print("Trying direct connection as last resort")
    start_tunnel_direct()


def find_available_port():
    """
    Find an available port on the local machine.
    
    Returns:
        int: An available port number
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start_proxytunnel(config):
    """
    Start the Proxytunnel process.
    
    Args:
        config (dict): Configuration dictionary from configure_proxytunnel
        
    Returns:
        subprocess.Popen: The running proxytunnel process
    """
    print(f"Starting Proxytunnel with command: {config['command']}")
    
    # Verify that the proxytunnel binary exists and is executable
    proxytunnel_path = config['command'].split()[0]
    if not os.path.exists(proxytunnel_path):
        print(f"ERROR: Proxytunnel binary not found at {proxytunnel_path}")
        return None
    
    if not os.access(proxytunnel_path, os.X_OK):
        print(f"ERROR: Proxytunnel binary at {proxytunnel_path} is not executable")
        try:
            os.chmod(proxytunnel_path, 0o755)
            print(f"Made {proxytunnel_path} executable")
        except Exception as e:
            print(f"Failed to make {proxytunnel_path} executable: {str(e)}")
            return None
    
    try:
        # Start the process
        process = subprocess.Popen(
            config['command'],
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Use separate threads to read stdout and stderr to avoid blocking
        from threading import Thread
        
        def read_output(pipe, prefix):
            try:
                for line in iter(pipe.readline, ''):
                    print(f"{prefix}: {line.strip()}")
            except Exception as e:
                print(f"Error reading from {prefix}: {str(e)}")
        
        # Start threads to read output
        Thread(target=read_output, args=(process.stdout, "PROXYTUNNEL")).start()
        Thread(target=read_output, args=(process.stderr, "PROXYTUNNEL ERROR")).start()
        
        # Wait a moment for the tunnel to establish
        time.sleep(2)
        
        # Check if the process is still running
        if process.poll() is not None:
            print(f"Proxytunnel process exited with code {process.returncode}")
            stderr_output = process.stderr.read()
            if stderr_output:
                print(f"Error output: {stderr_output}")
            return None
        
        print(f"Proxytunnel started successfully on local port {config['local_port']}")
        return process
    except Exception as e:
        print(f"Error starting Proxytunnel: {str(e)}")
        return None


def test_proxytunnel_connection(config):
    """
    Test if Proxytunnel is working correctly with the given configuration.
    
    Args:
        config (dict): Configuration dictionary from configure_proxytunnel
        
    Returns:
        bool: True if the test was successful, False otherwise
    """
    print("Testing Proxytunnel with a simple command...")
    
    # Start Proxytunnel
    process = start_proxytunnel(config)
    if not process:
        return False
    
    # Try different test URLs
    test_urls = [
        "https://github.com",
        "https://ifconfig.me",
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com"
    ]
    
    success = False
    
    # Set environment variable to use the local proxy
    env = os.environ.copy()
    env["HTTPS_PROXY"] = f"http://localhost:{config['local_port']}"
    
    # Try each URL
    for test_url in test_urls:
        print(f"Testing Proxytunnel with URL: {test_url}")
        
        # Try up to 3 times with each URL
        for attempt in range(1, 4):
            try:
                print(f"Attempt {attempt} of 3...")
                result = subprocess.run(
                    f"curl -s --connect-timeout 10 {test_url}",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    env=env
                )
                
                if result.returncode == 0:
                    response = result.stdout.decode('utf-8').strip()
                    print(f"Proxytunnel test successful! Response: {response}")
                    if response:  # Make sure we got a non-empty response
                        success = True
                        break
                    else:
                        print("Warning: Received empty response, may indicate partial connection")
                else:
                    print(f"Proxytunnel test failed with return code {result.returncode}")
                    error_output = result.stderr.decode('utf-8')
                    print(f"Error output: {error_output}")
                    
                    # Check for specific error messages that might help diagnose the issue
                    if "Could not resolve host" in error_output:
                        print("DNS resolution failed. This might be a DNS configuration issue.")
                    elif "Connection refused" in error_output:
                        print("Connection refused. The proxy might be blocking the connection.")
                    elif "timed out" in error_output:
                        print("Connection timed out. The proxy might be slow or blocking the connection.")
                    
                    # Wait before retry
                    if attempt < 3:
                        print(f"Waiting 2 seconds before retry...")
                        time.sleep(2)
            except subprocess.TimeoutExpired:
                print(f"Proxytunnel test timed out after 30 seconds on attempt {attempt}")
                if attempt < 3:
                    print(f"Waiting 2 seconds before retry...")
                    time.sleep(2)
            except Exception as e:
                print(f"Proxytunnel test failed with exception: {str(e)}")
                if attempt < 3:
                    print(f"Waiting 2 seconds before retry...")
                    time.sleep(2)
        
        if success:
            break
    
    # Clean up
    try:
        process.terminate()
        print("Terminated Proxytunnel process")
    except Exception as e:
        print(f"Error terminating Proxytunnel process: {str(e)}")
    
    return success

def configure_proxytunnel(proxy_url, proxy_port, target_host="vscode.dev", target_port=443):
    """
    Configure Proxytunnel settings.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        target_host (str): The target host to connect to (default: vscode.dev)
        target_port (int): The target port to connect to (default: 443)
        
    Returns:
        dict: Configuration dictionary with command and local port
    """
    # Find an available local port
    local_port = find_available_port()
    
    # Clean proxy URL
    clean_proxy_url = strip_protocol(proxy_url)
    
    # Determine the path to the proxytunnel binary
    proxytunnel_path = shutil.which("proxytunnel") or "./proxytunnel"
    
    # Create the proxytunnel command
    # Add -v for verbose output to help with debugging
    command = f"{proxytunnel_path} -p {clean_proxy_url}:{proxy_port} -d {target_host}:{target_port} -a {local_port} -v"
    
    return {
        "command": command,
        "local_port": local_port
    }


def configure_proxytunnel_advanced(proxy_url, proxy_port, target_host="vscode.dev",
                                 target_port=443, proxy_user=None, proxy_pass=None,
                                 use_ntlm=False, use_ssl=False):
    """
    Configure Proxytunnel with advanced settings.
    
    Args:
        proxy_url (str): The URL of the corporate proxy
        proxy_port (int): The port of the corporate proxy
        target_host (str): The target host to connect to
        target_port (int): The target port to connect to
        proxy_user (str): Username for proxy authentication
        proxy_pass (str): Password for proxy authentication
        use_ntlm (bool): Whether to use NTLM authentication
        use_ssl (bool): Whether to use SSL to connect to the proxy
        
    Returns:
        dict: Configuration dictionary with command and local port
    """
    # Find an available local port
    local_port = find_available_port()
    
    # Clean proxy URL
    clean_proxy_url = strip_protocol(proxy_url)
    
    # Determine the path to the proxytunnel binary
    proxytunnel_path = shutil.which("proxytunnel") or "./proxytunnel"
    
    # Start building the command
    # Add -v for verbose output to help with debugging
    command = f"{proxytunnel_path} -p {clean_proxy_url}:{proxy_port} -d {target_host}:{target_port} -a {local_port} -v"
    
    
    # Add authentication if provided
    if proxy_user and proxy_pass:
        if use_ntlm:
            command += f"  -u {proxy_user} -s {proxy_pass}"
        else:
            command += f" -P {proxy_user}:{proxy_pass}"
    
    # Add SSL if requested
    if use_ssl:
        command += " -E"
    
    return {
        "command": command,
        "local_port": local_port
    }

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
    # Add --accept-server-license-terms to the command
    base_command = "NODE_TLS_REJECT_UNAUTHORIZED=0 ./code tunnel --verbose --accept-server-license-terms --name colab-connect --log debug"
    
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
    
    # Create environment with SSL verification disabled
    env = os.environ.copy()
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
    env["CURL_CA_BUNDLE"] = ""  # Empty to disable curl certificate verification
    env["SSL_CERT_FILE"] = ""    # Empty to disable Python SSL certificate verification
    
    p = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env
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
    # Add --accept-server-license-terms to the command
    command = "NODE_TLS_REJECT_UNAUTHORIZED=0 ./code tunnel --accept-server-license-terms --verbose --name colab-connect --log debug"
    
    # Set environment variables to disable SSL verification
    env = os.environ.copy()
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
    env["CURL_CA_BUNDLE"] = ""  # Empty to disable curl certificate verification
    env["SSL_CERT_FILE"] = ""    # Empty to disable Python SSL certificate verification
    print(f"Starting VSCode tunnel directly: {command}")
    
    p = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env
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
                enable_proxy_dns=True, use_proxytunnel=False,
                proxy_user=None, proxy_pass=None, use_ntlm=False,
                use_ssl=False, use_fallbacks=True, ca_cert_path=None,
                disable_ssl_verification=False) -> None:
    """
    Connect to VSCode tunnel through a corporate proxy.
    
    Args:
        proxy_url (str): The URL of the corporate proxy (default: proxy.company.com)
        proxy_port (int): The port of the corporate proxy (default: 8080)
        enable_proxy_dns (bool): Whether to enable proxy_dns in proxychains config (default: True)
        use_proxytunnel (bool): Whether to use Proxytunnel instead of proxychains (default: False)
        proxy_user (str): Username for proxy authentication (default: None)
        proxy_pass (str): Password for proxy authentication (default: None)
        use_ntlm (bool): Whether to use NTLM authentication (default: False)
        use_ssl (bool): Whether to use SSL to connect to the proxy (default: False)
        use_fallbacks (bool): Whether to try fallback mechanisms if the primary method fails (default: True)
        ca_cert_path (str): Path to a custom CA certificate file (default: None)
        disable_ssl_verification (bool): Whether to disable SSL verification entirely (default: False)
    """

    # Set environment variables for custom CA certificate if provided
    if ca_cert_path:
        if os.path.exists(ca_cert_path):
            print(f"Using custom CA certificate: {ca_cert_path}")
            os.environ["NODE_EXTRA_CA_CERTS"] = ca_cert_path
            os.environ["SSL_CERT_FILE"] = ca_cert_path
            os.environ["REQUESTS_CA_BUNDLE"] = ca_cert_path
            os.environ["CURL_CA_BUNDLE"] = ca_cert_path
        else:
            print(f"Warning: Custom CA certificate file not found: {ca_cert_path}")
    
    # Disable SSL verification if requested (not recommended for production)
    if disable_ssl_verification:
        print("Warning: SSL verification is disabled. This is not secure for production use.")
        # Set multiple environment variables to disable SSL verification in different components
        os.environ["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
        os.environ["CURL_CA_BUNDLE"] = ""  # Empty to disable curl certificate verification
        os.environ["SSL_CERT_FILE"] = ""    # Empty to disable Python SSL certificate verification
        os.environ["GIT_SSL_NO_VERIFY"] = "1"  # For git operations
        os.environ["npm_config_strict_ssl"] = "false"  # For npm
    
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
#            extract_result = subprocess.run("unzip vscode_cli.zip", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    
    # Use direct connection with SSL verification disabled
    print("Using direct connection with SSL verification disabled...")
    
    try:
        # Set environment variables for the proxy
        os.environ["HTTPS_PROXY"] = f"http://{clean_proxy_url}:{proxy_port}"
        os.environ["HTTP_PROXY"] = f"http://{clean_proxy_url}:{proxy_port}"
        os.environ["http_proxy"] = f"http://{clean_proxy_url}:{proxy_port}"
        os.environ["https_proxy"] = f"http://{clean_proxy_url}:{proxy_port}"
        
        # Disable SSL verification with multiple environment variables
        os.environ["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
        os.environ["CURL_CA_BUNDLE"] = ""
        os.environ["SSL_CERT_FILE"] = ""
        os.environ["GIT_SSL_NO_VERIFY"] = "1"
        os.environ["npm_config_strict_ssl"] = "false"
        
        # Run the VSCode tunnel command directly
        command = "NODE_TLS_REJECT_UNAUTHORIZED=0 ./code tunnel --verbose --accept-server-license-terms --name colab-connect --log debug"
        print(f"Executing command: {command}")
        
        # Create environment with SSL verification disabled
        env = os.environ.copy()
        
        # Start the process
        p = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env
        )
        
        # Use separate threads to read stdout and stderr
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
    finally:
        pass


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


