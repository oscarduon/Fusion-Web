import sys
import os
import tifffile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate_tif_preview(input_path, output_path):
    try:
        data = tifffile.imread(input_path)

        valid_data = data[(data > -9000) & (data < 100000)]
        if len(valid_data) == 0:
            print("No valid data points found in TIF")
            return

        vmin = np.percentile(valid_data, 2)
        vmax = np.percentile(valid_data, 98)

        data = np.where((data <= -9000) | (data >= 100000), np.nan, data)

        plt.figure(figsize=(10, 10))
        plt.imshow(data, cmap="terrain", vmin=vmin, vmax=vmax)
        plt.axis("off")
        # PNG avoids the matplotlib/Pillow JPEG 'quality' incompatibility
        plt.savefig(output_path, bbox_inches="tight", pad_inches=0, dpi=150)
        plt.close()
        print(f"Successfully created preview: {output_path}")
    except Exception as e:
        print(f"Error generating preview: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tif_preview.py <input.tif> <output.png>")
        sys.exit(1)
    generate_tif_preview(sys.argv[1], sys.argv[2])
