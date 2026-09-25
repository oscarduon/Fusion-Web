import sys
import os
import tifffile
import matplotlib.pyplot as plt
import numpy as np

def generate_tif_preview(input_path, output_path):
    try:
        # Read the TIF data
        data = tifffile.imread(input_path)
        
        # Handle nodata values if they exist (usually very large or very small numbers in FUSION)
        # FUSION typically uses -9999.0 or similar for nodata
        valid_data = data[(data > -9000) & (data < 100000)]
        
        if len(valid_data) == 0:
            print("No valid data points found in TIF")
            return
            
        vmin = np.percentile(valid_data, 2)
        vmax = np.percentile(valid_data, 98)
        
        # Set nodata values to NaN so they render transparent/background
        data = np.where((data <= -9000) | (data >= 100000), np.nan, data)
        
        plt.figure(figsize=(10, 10))
        # Use 'terrain' colormap for elevation data
        plt.imshow(data, cmap='terrain', vmin=vmin, vmax=vmax)
        plt.axis('off')
        
        # Save as JPG
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0, dpi=150)
        plt.close()
        print(f"Successfully created preview: {output_path}")
    except Exception as e:
        print(f"Error generating preview: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tif_preview.py <input.tif> <output.jpg>")
        sys.exit(1)
        
    input_tif = sys.argv[1]
    output_jpg = sys.argv[2]
    
    generate_tif_preview(input_tif, output_jpg)
