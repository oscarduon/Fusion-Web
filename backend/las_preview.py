import sys
import laspy
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objs as go
import os

def generate_previews(las_path, out_jpg):
    try:
        if not os.path.exists(las_path):
            sys.exit(1)

        las = laspy.read(las_path)
        points = np.vstack((las.x, las.y, las.z)).transpose()
        
        # 1. 2D IMAGE
        if len(points) > 1000000:
            indices = np.random.choice(len(points), 1000000, replace=False)
            points_2d = points[indices]
            z_colors = las.z[indices]
        else:
            points_2d = points
            z_colors = las.z

        plt.style.use('dark_background')
        fig = plt.figure(figsize=(10, 8), dpi=100)
        ax = fig.add_subplot(111)
        scatter = ax.scatter(points_2d[:, 0], points_2d[:, 1], c=z_colors, s=0.1, cmap='terrain')
        plt.colorbar(scatter, label='Elevacion (m)')
        ax.set_aspect('equal')
        plt.title(f'Vista 2D de {os.path.basename(las_path)}')
        ax.axis('off')
        plt.savefig(out_jpg, format='jpeg', bbox_inches='tight', facecolor='#000000', )
        plt.close(fig)
        
        # 2. 3D HTML (Max 100k points for browser performance)
        if len(points) > 100000:
            indices_3d = np.random.choice(len(points), 100000, replace=False)
            points_3d = points[indices_3d]
            z_3d = las.z[indices_3d]
        else:
            points_3d = points
            z_3d = las.z
            
        fig_3d = go.Figure(data=[go.Scatter3d(
            x=points_3d[:,0],
            y=points_3d[:,1],
            z=points_3d[:,2],
            mode='markers',
            marker=dict(size=1.5, color=z_3d, colorscale='Viridis', opacity=0.8)
        )])
        fig_3d.update_layout(
            scene=dict(aspectmode='data', xaxis=dict(showbackground=False, showticklabels=False, title=''), yaxis=dict(showbackground=False, showticklabels=False, title=''), zaxis=dict(showbackground=False, showticklabels=False, title='')),
            margin=dict(l=0, r=0, b=0, t=0),
            paper_bgcolor='#131314',
            plot_bgcolor='#131314',
            font=dict(color='white')
        )
        html_path = las_path + "_3d.html"
        fig_3d.write_html(html_path, auto_play=False, include_plotlyjs='cdn')
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 2:
        generate_previews(sys.argv[1], sys.argv[2])
