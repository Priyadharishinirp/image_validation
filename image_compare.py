import cv2
import numpy as np
import imageio
import os
from PIL import Image

def resize_if_large(img, max_dim=3000):
    height, width = img.shape[:2]
    if height > max_dim or width > max_dim:
        scale = 0.5
        img = cv2.resize(img, (int(width * scale), int(height * scale)))
    return img

def visualize_color_difference(image_path1, image_path2):
    img1 = resize_if_large(cv2.imread(image_path1))
    img2 = resize_if_large(cv2.imread(image_path2))
    if img1 is None or img2 is None:
        return None, None

    img1_lab = cv2.cvtColor(img1, cv2.COLOR_BGR2Lab)
    img2_lab = cv2.cvtColor(img2, cv2.COLOR_BGR2Lab)

    delta_e = np.sqrt(np.sum((img1_lab - img2_lab) ** 2, axis=2))
    delta_e_normalized = cv2.normalize(delta_e, None, 0, 255, cv2.NORM_MINMAX)
    heatmap = cv2.applyColorMap(delta_e_normalized.astype(np.uint8), cv2.COLORMAP_JET)

    overlay_img1 = cv2.addWeighted(img1, 0.7, heatmap, 0.3, 0)
    overlay_img2 = cv2.addWeighted(img2, 0.7, heatmap, 0.3, 0)

    return overlay_img1, overlay_img2

def overlay_images_with_diff_and_transparency(image_path1, image_path2, alpha=0.7):
    img1 = resize_if_large(cv2.imread(image_path1))
    img2 = resize_if_large(cv2.imread(image_path2))
    if img1 is None or img2 is None:
        return None, None

    diff = cv2.absdiff(img1, img2)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_diff, 50, 255, cv2.THRESH_BINARY)
    mask = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

    img1_overlayed = img1.copy()
    img2_overlayed = img2.copy()

    img1_transparent = cv2.addWeighted(img1, alpha, np.zeros_like(img1), 0, 0)
    img2_transparent = cv2.addWeighted(img2, alpha, np.zeros_like(img2), 0, 0)

    img1_overlayed[mask == 255] = img2_transparent[mask == 255]
    img2_overlayed[mask == 255] = img1_transparent[mask == 255]

    return img1_overlayed, img2_overlayed

def compare_images(image_path1, image_path2, output_path1, output_path2, mode="both", alpha=0.7):
    results = {}

    if mode in ["both", "color"]:
        color_overlay1, color_overlay2 = visualize_color_difference(image_path1, image_path2)
        if color_overlay1 is not None and color_overlay2 is not None:
            path1 = output_path1.replace(".jpg", "_color1.jpg")
            path2 = output_path2.replace(".jpg", "_color2.jpg")
            cv2.imwrite(path1, color_overlay1)
            cv2.imwrite(path2, color_overlay2)
            results["color1"] = path1
            results["color2"] = path2

    if mode in ["both", "grayscale"]:
        gray_overlay1, gray_overlay2 = overlay_images_with_diff_and_transparency(image_path1, image_path2, alpha)
        if gray_overlay1 is not None and gray_overlay2 is not None:
            path1 = output_path1.replace(".jpg", "_gray1.jpg")
            path2 = output_path2.replace(".jpg", "_gray2.jpg")
            cv2.imwrite(path1, gray_overlay1)
            cv2.imwrite(path2, gray_overlay2)
            results["gray1"] = path1
            results["gray2"] = path2

    return results

def create_optimized_gif(image_path1, image_path2, gif_output_path, duration=1000, resize_factor=0.5, optimize=True):
    """
    Creates an optimized GIF alternating between two images.

    Args:
        image_path1: Path to the first image
        image_path2: Path to the second image
        gif_output_path: Path where the GIF will be saved
        duration: Duration each frame is displayed in milliseconds
        resize_factor: Factor to resize images (0.5 = half size)
        optimize: Whether to apply GIF optimization
    """
    img1 = cv2.imread(image_path1)
    img2 = cv2.imread(image_path2)

    if img1 is None or img2 is None:
        return None

    # Resize images to reduce file size
    height, width = img1.shape[:2]
    new_width = int(width * resize_factor)
    new_height = int(height * resize_factor)
    img1 = cv2.resize(img1, (new_width, new_height))
    img2 = cv2.resize(img2, (new_width, new_height))

    # Convert to RGB
    img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
    img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

    # Convert to PIL Images and reduce colors
    pil_img1 = Image.fromarray(img1_rgb).convert('P', palette=Image.ADAPTIVE, colors=128)
    pil_img2 = Image.fromarray(img2_rgb).convert('P', palette=Image.ADAPTIVE, colors=128)

    # Save as temporary files
    temp_path1 = "temp_img1.png"
    temp_path2 = "temp_img2.png"
    pil_img1.save(temp_path1)
    pil_img2.save(temp_path2)

    # Create GIF with optimizations
    frames = []
    frames.append(imageio.imread(temp_path1))
    frames.append(imageio.imread(temp_path2))

    imageio.mimsave(
        gif_output_path,
        frames,
        duration=duration,
        loop=0,
        optimize=optimize,
        quantizer='nq',  # neuquant quantizer for better color reduction
        palettesize=128  # Reduce palette size
    )

    # Clean up temporary files
    try:
        os.remove(temp_path1)
        os.remove(temp_path2)
    except:
        pass

    return gif_output_path

def create_pillow_gif(image_path1, image_path2, gif_output_path, duration=1000, resize_factor=0.5, colors=64):
    """
    Creates an optimized GIF using Pillow library for better compression.

    Args:
        image_path1: Path to the first image
        image_path2: Path to the second image
        gif_output_path: Path where the GIF will be saved
        duration: Duration each frame is displayed in milliseconds
        resize_factor: Factor to resize images (0.5 = half size)
        colors: Number of colors in the palette (lower = smaller file)
    """
    # Load images with PIL for better optimization
    img1 = Image.open(image_path1)
    img2 = Image.open(image_path2)

    # Resize to reduce file size
    new_width = int(img1.width * resize_factor)
    new_height = int(img1.height * resize_factor)
    img1 = img1.resize((new_width, new_height), Image.LANCZOS)
    img2 = img2.resize((new_width, new_height), Image.LANCZOS)

    # Convert to P mode (palette) with reduced colors for GIF efficiency
    img1 = img1.convert('P', palette=Image.ADAPTIVE, colors=colors)
    img2 = img2.convert('P', palette=Image.ADAPTIVE, colors=colors)

    # Save as GIF with optimizations
    img1.save(
        gif_output_path,
        save_all=True,
        append_images=[img2],
        optimize=True,
        duration=duration,
        loop=0
    )

    return gif_output_path
# Add this function back to your image_compare.py file:

def create_gif_from_images(image_path1, image_path2, gif_output_path, duration=1000.0):
    """
    Creates a GIF alternating between two images with the specified duration.

    Args:
        image_path1: Path to the first image
        image_path2: Path to the second image
        gif_output_path: Path where the GIF will be saved
        duration: Duration each frame is displayed in milliseconds (default: 1000 milliseconds)
    """
    img1 = resize_if_large(cv2.imread(image_path1))
    img2 = resize_if_large(cv2.imread(image_path2))
    if img1 is None or img2 is None:
        return None

    # Convert to RGB (GIFs use RGB)
    img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
    img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

    # Create a smaller version for the GIF (50% of original size)
    height, width = img1_rgb.shape[:2]
    new_width = int(width * 0.5)
    new_height = int(height * 0.5)
    img1_small = cv2.resize(img1_rgb, (new_width, new_height))
    img2_small = cv2.resize(img2_rgb, (new_width, new_height))

    # Create the animation
    imageio.mimsave(gif_output_path, [img1_small, img2_small], duration=duration, loop=0)

    return gif_output_path
# Example usage:
# compare_results = compare_images("image1.jpg", "image2.jpg", "output1.jpg", "output2.jpg")
#
# # Use either optimized function (Pillow version usually creates smaller files)
# gif_path = create_optimized_gif(
#     compare_results["color1"],
#     compare_results["color2"],
#     "comparison.gif",
#     duration=1000,  # milliseconds
#     resize_factor=0.4  # reduce to 40% of original size
# )
#
# # OR use the Pillow version (often gives better results)
# gif_path = create_pillow_gif(
#     compare_results["color1"],
#     compare_results["color2"],
#     "comparison.gif",
#     duration=1000,  # milliseconds
#     resize_factor=0.4,  # reduce to 40% of original size
#     colors=64  # use only 64 colors
# )
