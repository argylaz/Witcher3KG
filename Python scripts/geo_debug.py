import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch
from shapely.geometry import Point, Polygon, MultiLineString
import json
import xml.etree.ElementTree as ET

# --- 1. Transformation Functions (Finalized) ---
def calculate_affine_transform(game_coords, gis_coords):
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
    game_pt = np.array([point[0], point[1], 1])
    gis_pt = matrix @ game_pt
    return (gis_pt[0], gis_pt[1])

# --- 2. Your Control Point Data (Finalized) ---
GIS_CONTROL_POINTS = [
    (21.0036502117724, -677.368416076594), # Bottom-left corner
    (615.670143636147, -21.0036501982966),  # Top-right corner
    (21.0036502117724, -21.0036501982966),  # Top-left corner
    (615.670143636147, -677.368416076594)   # Bottom-right corner
]
GAME_CONTROL_POINTS = [
    (-890.57, -1424.50), # In-game bottom-left
    (2763.86, 2585.09),  # In-game top-right
    (-890.57, 2585.09),  # In-game top-left
    (2763.86, -1424.50)   # In-game bottom-right
]

# --- 3. DEFINITIVE Visualization Code with Correct MultiPolygon Parsing ---

def parse_esri_feature(feature):
    """
    Parses an entire Esri JSON feature into a list of shapely Polygons or Lines.
    Correctly handles MultiPolygons by creating a separate Polygon for each exterior ring.
    """
    geometry = feature.get('geometry', {})
    shapes = []
    
    if 'rings' in geometry and geometry['rings']:
        # This structure handles multipolygons, where each item in 'rings' is a separate polygon.
        for ring in geometry['rings']:
            # The actual coordinate list might be nested one level deeper.
            points = ring[0] if isinstance(ring[0][0], list) else ring
            try:
                if len(points) >= 4:
                    poly = Polygon(points)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    shapes.append(poly)
            except Exception:
                continue # Skip malformed rings
                
    elif 'paths' in geometry and geometry['paths']:
        shapes.append(MultiLineString(geometry['paths']))
        
    return shapes

def plot_polygon(ax, poly, **kwargs):
    """A robust function to plot any shapely Polygon, handling holes."""
    path = Path.make_compound_path(
        Path(np.asarray(poly.exterior.coords)[:, :2]),
        *[Path(np.asarray(ring.coords)[:, :2]) for ring in poly.interiors]
    )
    patch = PathPatch(path, **kwargs)
    ax.add_patch(patch)

def visualize(transform_matrix):
    """Generates the final map with robust MultiPolygon parsing."""
    
    gis_layers = {
        'Terrain': {'path': '../InfoFiles/novigrad_terrain.json', 'fc': '#A69078', 'alpha': 1.0, 'zorder': 1},
        'Swamps':  {'path': '../InfoFiles/novigrad_swamps.json',  'fc': '#556B2F', 'alpha': 0.8, 'zorder': 2},
        'Lakes':   {'path': '../InfoFiles/novigrad_lakes.json',   'fc': '#4682B4', 'alpha': 0.9, 'zorder': 3},
        'Cities':  {'path': '../InfoFiles/novigrad_cities.json',  'fc': '#708090', 'alpha': 0.7, 'zorder': 4},
        'Roads':   {'path': '../InfoFiles/novigrad_roads.json',   'color': '#8B4513', 'linewidth': 0.6, 'zorder': 5}
    }

    fig, ax = plt.subplots(figsize=(18, 22))
    ax.set_facecolor('#87CEEB')

    print("\nLoading and plotting GIS layers...")
    for layer_name, style in gis_layers.items():
        try:
            with open(style['path'], 'r', encoding='utf-16') as f: data = json.load(f)
            
            has_been_labeled = False
            for feature in data.get('features', []):
                label = layer_name if not has_been_labeled else "_nolegend_"
                
                # Use the new robust parser which returns a list of shapes
                shapes = parse_esri_feature(feature)
                for shape in shapes:
                    if shape.geom_type == 'Polygon':
                        plot_polygon(ax, shape, fc=style['fc'], alpha=style.get('alpha', 1.0), ec='darkslategray', linewidth=0.2, label=label, zorder=style['zorder'])
                        has_been_labeled = True
                    elif shape.geom_type == 'MultiLineString':
                        for part in shape.geoms:
                            x, y = part.xy
                            ax.plot(x, y, color=style['color'], linewidth=style['linewidth'], label=label, zorder=style['zorder'])
                        has_been_labeled = True
        except FileNotFoundError:
            print(f"  - WARNING: Could not find file for layer '{layer_name}': {style['path']}")

    # --- Load and Plot Map Pins ---
    game_pins_by_type = {}
    tree = ET.parse('../InfoFiles/MapPins.xml'); root = tree.getroot()
    for mappin in root.findall('.//world[@code="NO"]/mappin'):
        pos = mappin.find('position'); pin_type = mappin.get('type', 'Unknown')
        if pos is not None:
            if pin_type not in game_pins_by_type: game_pins_by_type[pin_type] = []
            game_pins_by_type[pin_type].append(Point(float(pos.get('x')), float(pos.get('y'))))
    color_map = { 'RoadSign': 'yellow', 'Harbor': 'orange', 'Teleport': 'gold', 'Blacksmith': '#363636', 'Armorer': '#696969', 'Whetstone': '#A9A9A9', 'Merchant': '#DA70D6', 'Herbalist': '#32CD32', 'GwentPlayer': '#8A2BE2', 'NoticeBoard': '#D2691E', 'PlaceOfPower': '#00FFFF', 'MonsterNest': '#FF0000', 'BanditCamp': '#8B0000', 'SideQuest': '#FF00FF', 'TreasureHuntMappin': '#FFD700', 'Entrance': 'white', 'default': '#FF69B4' }
    print("\nTransforming and plotting map pins by type...")
    for pin_type, points in sorted(game_pins_by_type.items()):
        transformed_pins = [Point(transform_point((p.x, p.y), transform_matrix)) for p in points]
        xs = [pt.x for pt in transformed_pins]; ys = [pt.y for pt in transformed_pins]
        color = color_map.get(pin_type, color_map['default'])
        ax.plot(xs, ys, 'o', color=color, markersize=5, label=pin_type, zorder=10, markeredgecolor='black', markeredgewidth=0.5)

    # --- Final plot styling (Unchanged) ---
    min_x, max_x = GIS_CONTROL_POINTS[0][0], GIS_CONTROL_POINTS[1][0]
    min_y, max_y = GIS_CONTROL_POINTS[0][1], GIS_CONTROL_POINTS[1][1]
    padding = 20
    ax.set_xlim(min_x - padding, max_x + padding)
    ax.set_ylim(min_y - padding, max_y + padding)
    ax.set_title('Final Map Alignment', fontsize=18)
    ax.set_xlabel('GIS X-Coordinate', fontsize=12)
    ax.set_ylabel('GIS Y-Coordinate', fontsize=12)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0., fontsize=10)
    ax.set_aspect('equal', 'box')
    fig.tight_layout(pad=1.5)
    plt.savefig('debug_map.png', bbox_inches='tight', dpi=200)
    print("\n--- Final diagnostic plot saved to debug_map_final.png ---")

if __name__ == '__main__':
    print("--- Running Standalone Diagnostic Script ---")
    if len(GAME_CONTROL_POINTS) < 3:
        print("!!! Please define at least 3 non-collinear control points to run the diagnostic. !!!")
    else:
        matrix = calculate_affine_transform(GAME_CONTROL_POINTS, GIS_CONTROL_POINTS)
        if matrix is not None:
            visualize(matrix)