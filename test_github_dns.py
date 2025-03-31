#!/usr/bin/env python3
"""
GitHub DNS Resolution Test Script

This script demonstrates how to use the GitHub DNS resolution functionality
to test if DNS resolution is causing issues with GitHub authentication.
"""

from colabconnect.colabconnect import test_github_dns, resolve_github_domains, add_to_hosts_file

def main():
    """Run the GitHub DNS resolution test."""
    print("=" * 60)
    print("GitHub DNS Resolution Test")
    print("=" * 60)
    print("\nThis script will:")
    print("1. Resolve key GitHub domains to their IP addresses")
    print("2. Add these entries to a local hosts file")
    print("3. Test connection to GitHub using the resolved IPs")
    print("\nThis can help verify if DNS resolution is causing issues with GitHub authentication.")
    print("=" * 60)
    
    # Test GitHub DNS resolution with default settings (local hosts file)
    success = test_github_dns(use_system_hosts=False, test_connection=True)
    
    if success:
        print("\n✅ GitHub DNS resolution test completed successfully!")
        print("You can now try running the VSCode tunnel with proxy_dns disabled:")
        print("\nfrom colabconnect.colabconnect import colabconnect")
        print("colabconnect(proxy_url='your.proxy.url', proxy_port=8080, enable_proxy_dns=False)")
    else:
        print("\n❌ GitHub DNS resolution test failed.")
        print("This suggests that the issue may not be related to DNS resolution,")
        print("or that there are other connectivity issues with GitHub.")
    
    return 0

if __name__ == "__main__":
    main()