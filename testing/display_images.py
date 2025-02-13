# display_images.py (Revised for Timestamped Directories)

import numpy as np
import matplotlib.pyplot as plt
import os
import glob
import argparse

def display_latest_images(base_directory="received_images"):
    """
    Loads and displays the latest set of raw RGB and NoIR images
    from the most recent timestamped subdirectory.
    """

    # Find the latest timestamped subdirectory
    subdirectories = [d for d in glob.glob(os.path.join(base_directory, "*")) if os.path.isdir(d)]
    if not subdirectories:
        print("No timestamped subdirectories found.")
        return
    latest_subdirectory = max(subdirectories, key=os.path.getctime)
    print(f"Displaying images from: {latest_subdirectory}")

    # Find the RGB image file
    rgb_files = glob.glob(os.path.join(latest_subdirectory, "raw_rgb_*.npy"))
    if not rgb_files:
        print("No RGB image file found in the latest subdirectory.")
        return
    rgb_file = rgb_files[0]
    rgb_image = np.load(rgb_file)

    # Find the NoIR image files
    noir_files = sorted(glob.glob(os.path.join(latest_subdirectory, "raw_noir_*.npy")))
    if len(noir_files) != 3:
        print(f"Expected 3 NoIR image files, found {len(noir_files)} in the latest subdirectory.")
        return

    # Create the subplot
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    # Display the RGB image
    axes[0].imshow(rgb_image.astype(np.uint8))
    axes[0].set_title("RGB Image")
    axes[0].axis('off')

    # Display the NoIR images
    for i, noir_file in enumerate(noir_files):
        noir_image = np.load(noir_file)
        # Normalize to 0-1 range for display
        noir_image_normalized = (noir_image - noir_image.min()) / (noir_image.max() - noir_image.min() + 1e-6)
        axes[i + 1].imshow(noir_image_normalized, cmap='gray')
        axes[i + 1].set_title(f"NoIR Image {i+1} ({os.path.basename(noir_file)})")
        axes[i + 1].axis('off')

    plt.tight_layout()
    plt.show()

def display_specific_images(directory):
    """
    Loads and displays images from a specific directory.
    """
    # Find the RGB image file
    rgb_files = glob.glob(os.path.join(directory, "raw_rgb_*.npy"))
    if not rgb_files:
        print(f"No RGB image file found in {directory}.")
        return
    rgb_file = rgb_files[0]
    rgb_image = np.load(rgb_file)

    # Find the NoIR image files
    noir_files = sorted(glob.glob(os.path.join(directory, "raw_noir_*.npy")))
    if len(noir_files) != 3:
        print(f"Expected 3 NoIR image files, found {len(noir_files)} in {directory}.")
        return

    # Create and display the subplot (same as in display_latest_images)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()

    axes[0].imshow(rgb_image.astype(np.uint8))
    axes[0].set_title("RGB Image")
    axes[0].axis('off')

    for i, noir_file in enumerate(noir_files):
        noir_image = np.load(noir_file)
        noir_image_normalized = (noir_image - noir_image.min()) / (noir_image.max() - noir_image.min() + 1e-6)
        axes[i + 1].imshow(noir_image_normalized, cmap='gray')
        axes[i + 1].set_title(f"NoIR Image {i+1} ({os.path.basename(noir_file)})")
        axes[i + 1].axis('off')

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Display multispectral images.")
    parser.add_argument("-d", "--directory", type=str, help="Specific directory to display images from.")
    args = parser.parse_args()

    if args.directory:
        display_specific_images(args.directory)
    else:
        display_latest_images()


# how to run

"""
# Display Latest Images: Just run python display_images.py.

# Display Images from a Specific Directory: 
Run python display_images.py -d <directory_name>, 
replacing <directory_name> with the name of the timestamped directory 
(e.g., python display_images.py -d 20240119_153045).
"""