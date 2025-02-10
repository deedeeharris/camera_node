import requests

def capture_image(camera_ip, port=5001):
    """
    Request an image from the camera node and save it as a DNG file.
    
    Args:
        camera_ip (str): The IP address of the camera node.
        port (int): The port number the camera node is running on.
    """
    # Construct the URL for the /capture endpoint
    url = f"http://{camera_ip}:{port}/capture"
    
    # Set the query parameter to return the file directly
    params = {"return_file": True}
    
    try:
        # Make the POST request to capture the image
        print(f"Requesting image from {url} ...")
        response = requests.post(url, params=params)
        response.raise_for_status()  # Raise an error for bad status codes
        
        # Optionally, you can try to extract a suggested filename from headers (if provided)
        filename = "captured_image.dng"
        if "Content-Disposition" in response.headers:
            # The header may look like: 'attachment; filename="capture_20250203_134500.dng"'
            disposition = response.headers["Content-Disposition"]
            parts = disposition.split("filename=")
            if len(parts) > 1:
                filename = parts[1].strip(' "')
        
        # Write the content to a file
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"Image saved as {filename}")
    
    except Exception as e:
        print("Failed to capture image:", e)

if __name__ == "__main__":
    # Replace this with the actual IP address of your camera node
    camera_node_ip = "192.168.195.70"
    capture_image(camera_node_ip)
