import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon
import json

# --- 1. The Numerically Stable Transformation Function ---
def calculate_affine_transform(game_coords, gis_coords):
    """
    Calculates the 2D affine transformation matrix using a robust
    least-squares method that is stable for 3 or more points.
    """
    game_pts = np.array(game_coords)
    gis_pts = np.array(gis_coords)
    
    # Pad the game coordinates with a column of ones to handle translation
    A = np.hstack([game_pts, np.ones((game_pts.shape[0], 1))])
    
    # Use least squares to solve for the transformation parameters for X and Y
    # This is more robust than np.linalg.solve for this problem
    try:
        params_x, _, _, _ = np.linalg.lstsq(A, gis_pts[:, 0], rcond=None)
        params_y, _, _, _ = np.linalg.lstsq(A, gis_pts[:, 1], rcond=None)
    except np.linalg.LinAlgError as e:
        print(f"!!! FATAL LINALG ERROR: {e} !!!")
        print("This means your control points are still collinear. You must choose points that form a triangle.")
        return None
    
    # The solution gives us the rows of the 2x3 transformation matrix
    transform_matrix = np.array([params_x, params_y])
    
    print("\n--- Calculated Transformation Matrix ---")
    print(transform_matrix)
    return transform_matrix

def transform_point(point, matrix):
    """Applies the affine transformation to a single point."""
    game_pt = np.array([point[0], point[1], 1])
    gis_pt = matrix @ game_pt
    return (gis_pt[0], gis_pt[1])

# --- 2. Your Control Point Data ---

# Define the extents of the game map (approximate values) not used in the code
# game_map_y_extent = 2500.0
# game_map_x_extent = game_map_y_extent * 0.906


GIS_CONTROL_POINTS = [
    # (214.811774233621, -139.481429540745),  # Novigrad polygon left peak (/\)
    # (201.451320267247, -520.246408777688),  # Oreton polygon right-most corner
    # (369.613548687602, -306.024182113144)   # Codger's Quarry polygon left-most corner

    (21.0036502117724, -21.0036501982966), # top left corner of playable area 
    (615.670143636147, -677.368416076594), # bottom right corner of playable area
    (21.0036502117724, -677.368416076594), # bottom left corner of playable area
    (615.670143636147, -21.0036501982966)  # top right corner of playable area
]

# Inverting the Y-axis of the game coordinates to match the GIS system's direction.
GAME_CONTROL_POINTS = [
    # (329.77, -187.0),   # Novigrad Y: 187 -> -187
    # (199.45, 455.0),   # Oreton Y: -455 -> 455
    # (1199.0, -852.0)    # Codger's Quarry Y: 852 -> -852

    (-768.57, 2685.09), # top left corner of playable area 
    (2583.86, -1294.50), # bottom right corner of playable area
    (-768.57, -1294.50), # bottom left corner of playable area
    (2583.86, 2685.09)   # top right corner of playable area
]

# --- 3. Visualization Code ---
def visualize(transform_matrix):
    """Generates the debug_map.png image."""
    
    # Load the GIS polygons directly from the source file
    polygons = []
    with open('../InfoFiles/novigrad_cities.json', 'r', encoding='utf-16') as f:
        data = json.load(f)
        for feature in data.get('features', []):
            if 'rings' in feature.get('geometry', {}):
                polygons.append(Polygon(feature['geometry']['rings'][0]))

    # Load the game map pins directly from the source file
    import xml.etree.ElementTree as ET
    game_pins = []
    tree = ET.parse('../InfoFiles/MapPins.xml')
    root = tree.getroot()
    for mappin in root.findall('.//mappin'):
        pos = mappin.find('position')
        if pos is not None:
            game_pins.append(Point(float(pos.get('x')), float(pos.get('y'))))

    # Transform the game pins to GIS coordinates
    transformed_pins = [Point(transform_point((p.x, p.y), transform_matrix)) for p in game_pins]

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 12))
    for poly in polygons:
        x, y = poly.exterior.xy
        ax.fill(x, y, alpha=0.5, fc='blue', ec='black')
    
    if transformed_pins:
        xs = [pt.x for pt in transformed_pins]
        ys = [pt.y for pt in transformed_pins]
        ax.plot(xs, ys, 'ro', markersize=2, label='Transformed Map Pins')

    ax.set_title('Diagnostic Map Alignment')
    ax.set_xlabel('GIS X-Coordinate')
    ax.set_ylabel('GIS Y-Coordinate')
    ax.legend()
    ax.set_aspect('equal', 'box')
    plt.savefig('debug_map.png')
    print("\n--- Diagnostic plot saved to debug_map.png ---")

if __name__ == '__main__':
    print("--- Running Standalone Diagnostic Script ---")
    
    # Use a minimum of 3 NON-COLLINEAR points for stability
    matrix = calculate_affine_transform(GAME_CONTROL_POINTS, GIS_CONTROL_POINTS)
    
    if matrix is not None:
        visualize(matrix)
    else:
        print("Could not generate visualization because transformation failed.")