import sys
import os
import laspy
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate_preview(las_path, out_png):
    try:
        if not os.path.exists(las_path):
            sys.exit(1)

        las = laspy.read(las_path)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        z = np.asarray(las.z)
        n = len(x)

        if n > 1000000:
            idx = np.random.choice(n, 1000000, replace=False)
            x, y, z = x[idx], y[idx], z[idx]

        plt.style.use("dark_background")
        fig = plt.figure(figsize=(10, 8), dpi=100)
        ax = fig.add_subplot(111)
        scatter = ax.scatter(x, y, c=z, s=0.1, cmap="terrain")
        plt.colorbar(scatter, label="Elevación (m)")
        ax.set_aspect("equal")
        plt.title(f"Vista 2D de {os.path.basename(las_path)}")
        ax.axis("off")
        # PNG avoids the matplotlib/Pillow JPEG 'quality' incompatibility
        plt.savefig(out_png, bbox_inches="tight", facecolor="#000000")
        plt.close(fig)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 2:
        generate_preview(sys.argv[1], sys.argv[2])
