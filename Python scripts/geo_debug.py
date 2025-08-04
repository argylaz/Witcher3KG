import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon, LineString, MultiLineString, mapping
import json
import xml.etree.ElementTree as ET
import glob

# --- 1. The Numerically Stable Transformation Function (Unchanged) ---
def calculate_affine_transform(game_coords, gis_coords):
    """
    Calculates the 2D affine transformation matrix using a robust
    least-squares method that is stable for 3 or more points.
    """
    game_pts = np.array(game_coords)
    gis_pts = np.array(gis_coords)
    A = np.hstack([game_pts, np.ones((game_pts.shape[0], 1))])
    try:
        params_x, _, _, _ = np.linalg.lstsq(A, gis_pts[:, 0], rcond=None)
        params_y, _, _, _ = np.linalg.lstsq(A, gis_pts[:, 1], rcond=None)
    except np.linalg.LinAlgError as e:
        print(f"!!! FATAL LINALG ERROR: {e} !!!"); return None
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
# These are the manually found coordinates that correctly align the maps.
GIS_CONTROL_POINTS = [
    (21.0036502117724, -21.0036501982966),  # Top-left corner
    (615.670143636147, -677.368416076594), # Bottom-right corner
    (21.0036502117724, -677.368416076594), # Bottom-left corner
    (615.670143636147, -21.0036501982966)   # Top-right corner
]

GAME_CONTROL_POINTS = [
    (-768.57, 2685.09),  # In-game top-left corner
    (2583.86, -1294.50), # In-game bottom-right corner
    (-768.57, -1294.50), # In-game bottom-left corner
    (2583.86, 2685.09)   # In-game top-right corner
]

# --- 3. Upgraded Visualization Code ---
def visualize(transform_matrix):
    """
    Generates a rich, multi-layered debug map with color-coded pins.
    """
    
    # --- Load all GIS Polygon and Polyline data ---
    gis_shapes = {'polygons': [], 'lines': []}
    # Use glob to find all json files in the directory
    gis_files = glob.glob('../InfoFiles/*.json')
    print(f"\nFound GIS files to load: {gis_files}")

    for file_path in gis_files:
        print(f"  - Loading {file_path}...")
        with open(file_path, 'r', encoding='utf-16') as f:
            data = json.load(f)
            for feature in data.get('features', []):
                geometry = feature.get('geometry', {})
                if 'rings' in geometry:
                    gis_shapes['polygons'].append(Polygon(geometry['rings'][0]))
                elif 'paths' in geometry:
                    gis_shapes['lines'].append(MultiLineString(geometry['paths']))

    # --- Load and Categorize Game Map Pins ---
    game_pins_by_type = {}
    tree = ET.parse('../InfoFiles/MapPins.xml')
    root = tree.getroot()
    for mappin in root.findall('.//world[@code="NO"]/mappin'): # Only load Novigrad/Velen pins
        pos = mappin.find('position')
        pin_type = mappin.get('type', 'Unknown')
        if pos is not None:
            if pin_type not in game_pins_by_type:
                game_pins_by_type[pin_type] = []
            game_pins_by_type[pin_type].append(Point(float(pos.get('x')), float(pos.get('y'))))

    # --- Define a Color Map for Pin Types ---
    # You can customize these colors
    color_map = {
        'RoadSign': 'yellow', 'Harbor': 'orange',
        'Blacksmith': 'black', 'Armorer': 'dimgray', 'Whetstone': 'gray',
        'Merchant': 'purple', 'Herbalist': 'green',
        'NoticeBoard': 'brown',
        'PlaceOfPower': 'cyan',
        'MonsterNest': 'red', 'BanditCamp': 'darkred',
        'SideQuest': 'magenta', 'TreasureHuntMappin': 'gold',
        'Entrance': 'white',
        'default': 'lime' # A default color for any other type
    }

    # --- Create the Plot ---
    fig, ax = plt.subplots(figsize=(15, 20)) # Make the plot larger
    
    # Plot all GIS Polygons
    for poly in gis_shapes['polygons']:
        x, y = poly.exterior.xy
        ax.fill(x, y, alpha=0.4, fc='cornflowerblue', ec='black')
        
    # Plot all GIS Lines (Roads)
    for line in gis_shapes['lines']:
        for part in line.geoms:
            x, y = part.xy
            ax.plot(x, y, color='saddlebrown', linewidth=0.8)

    # Transform and plot each category of map pins with its own color
    print("\nTransforming and plotting map pins by type...")
    for pin_type, points in game_pins_by_type.items():
        transformed_pins = [Point(transform_point((p.x, p.y), transform_matrix)) for p in points]
        xs = [pt.x for pt in transformed_pins]
        ys = [pt.y for pt in transformed_pins]
        color = color_map.get(pin_type, color_map['default'])
        ax.plot(xs, ys, 'o', color=color, markersize=3, label=pin_type)
        print(f"  - Plotted {len(points)} '{pin_type}' pins in {color}")

    ax.set_title('Full Diagnostic Map Alignment', fontsize=16)
    ax.set_xlabel('GIS X-Coordinate')
    ax.set_ylabel('GIS Y-Coordinate')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.) # Place legend outside
    ax.set_aspect('equal', 'box')
    ax.set_facecolor('lightsteelblue') # Add a background color
    fig.tight_layout() # Adjust layout to make room for legend
    plt.savefig('debug_map_full.png', bbox_inches='tight')
    print("\n--- Full diagnostic plot saved to debug_map_full.png ---")

if __name__ == '__main__':
    print("--- Running Standalone Diagnostic Script ---")
    if len(GAME_CONTROL_POINTS) < 3:
        print("!!! Please define at least 3 non-collinear control points to run the diagnostic. !!!")
    else:
        matrix = calculate_affine_transform(GAME_CONTROL_POINTS, GIS_CONTROL_POINTS)
        if matrix is not None:
            visualize(matrix)