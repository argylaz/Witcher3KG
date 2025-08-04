import xml.etree.ElementTree as ET
import re
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL

# --- Configuration ---
ONTOLOGY_PREFIX = "witcher"
BASE_URI = f"http://cgi.di.uoa.gr/{ONTOLOGY_PREFIX}/ontology#"

# Initialize the graph and bind namespaces
g = Graph()
witcher = Namespace(BASE_URI)
dbr = Namespace(f"http://cgi.di.uoa.gr/{ONTOLOGY_PREFIX}/resource/") # Resource namespace
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
g.bind("geo", GEO)
g.bind("witcher", witcher)
g.bind("dbr", dbr)
g.bind("owl", OWL)
g.bind("rdfs", RDFS)

# --- Helper Functions ---
def sanitize_for_uri(title):
    """Replaces all non-alphanumeric characters with underscores."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', title)

def extract_full_text(element):
    """Extracts text from an element, including from its children's tails."""
    if element is None: return ""
    return "".join(element.itertext())

# --- 1. Generate Class Hierarchy from Wiki Categories ---
print("Parsing wiki categories to build class hierarchy...")
try:
    tree = ET.parse('../Wiki_Dump_Namespaces/namespace_14_Category.xml')
    root = tree.getroot()

    for page in root.findall('page'):
        title_text = page.find('title').text.replace("Category:", "")
        class_uri = witcher[sanitize_for_uri(title_text)]
        
        # Declare the class
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.label, Literal(title_text.replace("_", " "))))
        
        # Find and add parent class relationships
        text = extract_full_text(page.find('text'))
        parent_matches = re.findall(r'\[\[Category:([^\]]+)\]\]', text)
        for parent_title in parent_matches:
            parent_uri = witcher[sanitize_for_uri(parent_title)]
            g.add((class_uri, RDFS.subClassOf, parent_uri))
    print("Successfully generated class hierarchy from categories.")

except FileNotFoundError:
    print("Warning: Category XML file not found. No class hierarchy will be built.")

# --- 2. Manually Define Mappin Ontology and Relationships ---
print("Adding specific axioms for map pins and game concepts...")

# Define a top-level class for all map pins
mappin_base_class = witcher.Mappin
g.add((mappin_base_class, RDF.type, OWL.Class))
g.add((mappin_base_class, RDFS.label, Literal("Map Pin")))
g.add((mappin_base_class, RDF.type, GEO.Feature))  # Every map pin is also a geographic feature
g.add((mappin_base_class, RDFS.comment, Literal("Base class for all map pins in The Witcher 3.")))


# Define functional sub-categories of map pins
crafting_station = dbr.Crafting_Station
g.add((crafting_station, RDFS.subClassOf, mappin_base_class))
g.add((crafting_station, RDFS.label, Literal("Crafting Station")))

road_sign = witcher.RoadSign
g.add((road_sign, RDFS.subClassOf, mappin_base_class))
g.add((road_sign, RDFS.label, Literal("Road Sign")))

# Define specific mappin types as subclasses
g.add((witcher.Blacksmith, RDFS.subClassOf, crafting_station))
g.add((witcher.Blacksmith, OWL.sameAs, witcher.Blacksmiths))    # Link to the main Blacksmith class
g.add((witcher.Armorer, RDFS.subClassOf, crafting_station))     
g.add((witcher.Armorer, OWL.sameAs, witcher.Armorers))          # Link to the main Armorer class
g.add((witcher.Whetstone, RDFS.subClassOf, crafting_station))
g.add((witcher.AlchemyTable, RDFS.subClassOf, crafting_station))
g.add((witcher.Grindstone, RDFS.subClassOf, witcher.Whetstone)) # A Grindstone is a type of Whetstone

# Define specific mappin types
g.add((witcher.NoticeBoard, RDFS.subClassOf, mappin_base_class))
g.add((witcher.NoticeBoard, RDFS.label, Literal("Notice Board")))
g.add((witcher.NoticeBoard, OWL.sameAs, witcher.The_Witcher_3_notice_boards))

g.add((witcher.SideQuest, RDFS.subClassOf, mappin_base_class))
g.add((witcher.SideQuest, RDFS.label, Literal("Side Quest")))
g.add((witcher.SideQuest, OWL.sameAs, witcher.The_Witcher_3_secondary_quests))

g.add((witcher.PlaceOfPower, RDFS.subClassOf, mappin_base_class))
g.add((witcher.PlaceOfPower, RDFS.label, Literal("Place of Power")))

g.add((witcher.MonterNest, RDFS.subClassOf, mappin_base_class))
g.add((dbr.MonterNest, RDFS.label, Literal("Monster Nest")))

g.add((witcher.Harbor, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Harbor, RDFS.label, Literal("Harbor")))

g.add((witcher.BanditCampfire, RDFS.subClassOf, mappin_base_class))
g.add((witcher.BanditCampfire, RDFS.label, Literal("Bandit Campfire")))

g.add((witcher.Contraband, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Contraband, RDFS.label, Literal("Contraband")))

g.add((witcher.Entrance, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Entrance, RDFS.label, Literal("Entrance")))

g.add((witcher.Merchant, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Merchant, RDFS.label, Literal("Merchant")))
g.add((witcher.Merchant, OWL.sameAs, witcher.Merchants))

g.add((witcher.PlayerStash, RDFS.subClassOf, mappin_base_class))  
g.add((witcher.PlayerStash, RDFS.label, Literal("Player Stash")))

g.add((witcher.RescuingTown, RDFS.subClassOf, mappin_base_class))
g.add((witcher.RescuingTown, RDFS.label, Literal("Rescuing Town")))

g.add((witcher.SpoilsOfWar, RDFS.subClassOf, mappin_base_class))
g.add((witcher.SpoilsOfWar, RDFS.label, Literal("Spoils of War")))

g.add((witcher.TreasureHuntMappin, RDFS.subClassOf, mappin_base_class))   
g.add((witcher.TreasureHuntMappin, RDFS.label, Literal("Treasure Hunt Map Pin")))

g.add((witcher.TreasureQuest, RDFS.subClassOf, mappin_base_class))
g.add((witcher.TreasureQuest, RDFS.label, Literal("Treasure Quest")))
g.add((witcher.TreasureQuest, OWL.sameAs, witcher.The_Witcher_3_treasure_hunts))

g.add((witcher.ArmorRepairTable, RDFS.subClassOf, crafting_station))
g.add((witcher.ArmorRepairTable, RDFS.label, Literal("Armor Repair Table")))

g.add((witcher.BanditCampfire, RDFS.subClassOf, mappin_base_class))
g.add((witcher.BanditCampfire, RDFS.label, Literal("Bandit Camp Fire")))

g.add((witcher.BossAndTreasure, RDFS.subClassOf, mappin_base_class))
g.add((witcher.BossAndTreasure, RDFS.label, Literal("Boss And Treasure")))

g.add((witcher.ChapterQuest, RDFS.subClassOf, mappin_base_class))
g.add((witcher.ChapterQuest, RDFS.label, Literal("Chapter Quest")))

g.add((witcher.DungeonCrawl, RDFS.subClassOf, mappin_base_class))
g.add((witcher.DungeonCrawl, RDFS.label, Literal("DungeonCrawl")))

g.add((witcher.Enchant, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Enchant, RDFS.label, Literal("Enchant")))

g.add((witcher.GwentPlayer, RDFS.subClassOf, mappin_base_class))
g.add((witcher.GwentPlayer, RDFS.label, Literal("Gwent Player")))
g.add((witcher.GwentPlayer, RDFS.subClassOf, witcher.Gwent))  # Link to the main Gwent class

g.add((witcher.GwentSeller, RDFS.subClassOf, mappin_base_class))
g.add((witcher.GwentSeller, RDFS.label, Literal("Gwent Seller")))
g.add((witcher.GwentSeller, RDFS.subClassOf, witcher.Gwent))  # Link to the main Gwent class

g.add((witcher.Herbalist, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Herbalist, RDFS.label, Literal("Herbalist")))
g.add((witcher.Herbalist, OWL.sameAs, witcher.Herbalists))  # Link to the main Herbalist class

g.add((witcher.HorseRacing, RDFS.subClassOf, mappin_base_class))
g.add((witcher.HorseRacing, RDFS.label, Literal("Horse Racing")))

g.add((witcher.MonsterQuest, RDFS.subClassOf, mappin_base_class))
g.add((witcher.MonsterQuest, RDFS.label, Literal("Monster Quest")))

g.add((witcher.Teleport, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Teleport, RDFS.label, Literal("Teleport")))

g.add((witcher.Bed, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Bed, RDFS.label, Literal("Bed")))

g.add((witcher.Hideout, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Hideout, RDFS.label, Literal("Hideout")))

g.add((witcher.InfestedVineyard, RDFS.subClassOf, mappin_base_class))
g.add((witcher.InfestedVineyard, RDFS.label, Literal("Infested Vineyard")))
g.add((witcher.InfestedVineyard, RDFS.subClassOf, witcher.Vineyards))

g.add((witcher.KnightErrant, RDFS.subClassOf, mappin_base_class))
g.add((witcher.KnightErrant, RDFS.label, Literal("Knight Errant")))

g.add((witcher.MutagenDismantle, RDFS.subClassOf, mappin_base_class))
g.add((witcher.MutagenDismantle, RDFS.label, Literal("Mutagen Dismantle")))

g.add((witcher.Plegmund, RDFS.subClassOf, mappin_base_class))
g.add((witcher.Plegmund, RDFS.label, Literal("Plegmund")))

g.add((witcher.SignalingStake, RDFS.subClassOf, mappin_base_class))
g.add((witcher.SignalingStake, RDFS.label, Literal("Signaling Stake")))

g.add((witcher.WineContract, RDFS.subClassOf, mappin_base_class))
g.add((witcher.WineContract, RDFS.label, Literal("Wine Contract")))


# Link game concepts (professions) to the mappin types they use
# This creates the crucial connection between the person and the map icon.
uses_mappin_type = witcher.usesMappinType
g.add((uses_mappin_type, RDF.type, OWL.ObjectProperty))
g.add((uses_mappin_type, RDFS.label, Literal("uses mappin type")))

# The Blacksmith profession uses the Blacksmith mappin type (Similarly for other professions)
g.add((dbr.Blacksmith, uses_mappin_type, witcher.Blacksmith))
g.add((dbr.Armorer, uses_mappin_type, witcher.Armorer))

print("Ontology augmentation complete.")

# --- 3. Save the Combined Ontology ---
with open('../RDF/Classes.ttl', 'w', encoding='utf-8') as f:
    f.write(g.serialize(format='turtle'))

print(f"\nSuccessfully generated enriched ontology file at '../RDF/Classes.ttl'")