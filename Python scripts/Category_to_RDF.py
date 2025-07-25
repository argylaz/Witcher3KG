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
mappin_base_class = dbr.Mappin
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
g.add((dbr.Blacksmith, RDFS.subClassOf, crafting_station))
g.add((dbr.Blacksmith, OWL.sameAs, witcher.Blacksmiths))    # Link to the main Blacksmith class
g.add((dbr.Armorer, RDFS.subClassOf, crafting_station))     
g.add((dbr.Armorer, OWL.sameAs, witcher.Armorers))          # Link to the main Armorer class
g.add((dbr.Whetstone, RDFS.subClassOf, crafting_station))
g.add((dbr.AlchemyTable, RDFS.subClassOf, crafting_station))
g.add((dbr.Grindstone, RDFS.subClassOf, witcher.Whetstone)) # A Grindstone is a type of Whetstone

# Define specific mappin types
g.add((dbr.NoticeBoard, RDFS.subClassOf, mappin_base_class))
g.add((dbr.NoticeBoard, RDFS.label, Literal("Notice Board")))
g.add((dbr.NoticeBoard, OWL.sameAs, witcher.The_Witcher_3_notice_boards))

g.add((dbr.SideQuest, RDFS.subClassOf, mappin_base_class))
g.add((dbr.SideQuest, RDFS.label, Literal("Side Quest")))
g.add((dbr.SideQuest, OWL.sameAs, witcher.The_Witcher_3_secondary_quests))

g.add((dbr.PlaceOfPower, RDFS.subClassOf, mappin_base_class))
g.add((dbr.PlaceOfPower, RDFS.label, Literal("Place of Power")))

g.add((dbr.MonterNest, RDFS.subClassOf, mappin_base_class))
g.add((dbr.MonterNest, RDFS.label, Literal("Monster Nest")))

g.add((dbr.Harbor, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Harbor, RDFS.label, Literal("Harbor")))

g.add((dbr.BanditCampfire, RDFS.subClassOf, mappin_base_class))
g.add((dbr.BanditCampfire, RDFS.label, Literal("Bandit Campfire")))

g.add((dbr.Contraband, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Contraband, RDFS.label, Literal("Contraband")))

g.add((dbr.Entrance, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Entrance, RDFS.label, Literal("Entrance")))

g.add((dbr.Merchant, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Merchant, RDFS.label, Literal("Merchant")))
g.add((dbr.Merchant, OWL.sameAs, witcher.Merchants))

g.add((dbr.PlayerStash, RDFS.subClassOf, mappin_base_class))  
g.add((dbr.PlayerStash, RDFS.label, Literal("Player Stash")))

g.add((dbr.RescuingTown, RDFS.subClassOf, mappin_base_class))
g.add((dbr.RescuingTown, RDFS.label, Literal("Rescuing Town")))

g.add((dbr.SpoilsOfWar, RDFS.subClassOf, mappin_base_class))
g.add((dbr.SpoilsOfWar, RDFS.label, Literal("Spoils of War")))

g.add((dbr.TreasureHuntMappin, RDFS.subClassOf, mappin_base_class))   
g.add((dbr.TreasureHuntMappin, RDFS.label, Literal("Treasure Hunt Map Pin")))

g.add((dbr.TreasureQuest, RDFS.subClassOf, mappin_base_class))
g.add((dbr.TreasureQuest, RDFS.label, Literal("Treasure Quest")))
g.add((dbr.TreasureQuest, OWL.sameAs, witcher.The_Witcher_3_treasure_hunts))

g.add((dbr.ArmorRepairTable, RDFS.subClassOf, crafting_station))
g.add((dbr.ArmorRepairTable, RDFS.label, Literal("Armor Repair Table")))

g.add((dbr.BanditCampfire, RDFS.subClassOf, mappin_base_class))
g.add((dbr.BanditCampfire, RDFS.label, Literal("Bandit Camp Fire")))

g.add((dbr.BossAndTreasure, RDFS.subClassOf, mappin_base_class))
g.add((dbr.BossAndTreasure, RDFS.label, Literal("Boss And Treasure")))

g.add((dbr.ChapterQuest, RDFS.subClassOf, mappin_base_class))
g.add((dbr.ChapterQuest, RDFS.label, Literal("Chapter Quest")))

g.add((dbr.DungeonCrawl, RDFS.subClassOf, mappin_base_class))
g.add((dbr.DungeonCrawl, RDFS.label, Literal("DungeonCrawl")))

g.add((dbr.Enchant, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Enchant, RDFS.label, Literal("Enchant")))

g.add((dbr.GwentPlayer, RDFS.subClassOf, mappin_base_class))
g.add((dbr.GwentPlayer, RDFS.label, Literal("Gwent Player")))
g.add((dbr.GwentPlayer, RDFS.subClassOf, witcher.Gwent))  # Link to the main Gwent class

g.add((dbr.GwentSeller, RDFS.subClassOf, mappin_base_class))
g.add((dbr.GwentSeller, RDFS.label, Literal("Gwent Seller")))
g.add((dbr.GwentSeller, RDFS.subClassOf, witcher.Gwent))  # Link to the main Gwent class

g.add((dbr.Herbalist, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Herbalist, RDFS.label, Literal("Herbalist")))
g.add((dbr.Herbalist, OWL.sameAs, witcher.Herbalists))  # Link to the main Herbalist class

g.add((dbr.HorseRacing, RDFS.subClassOf, mappin_base_class))
g.add((dbr.HorseRacing, RDFS.label, Literal("Horse Racing")))

g.add((dbr.MonsterQuest, RDFS.subClassOf, mappin_base_class))
g.add((dbr.MonsterQuest, RDFS.label, Literal("Monster Quest")))

g.add((dbr.Teleport, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Teleport, RDFS.label, Literal("Teleport")))

g.add((dbr.Bed, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Bed, RDFS.label, Literal("Bed")))

g.add((dbr.Hideout, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Hideout, RDFS.label, Literal("Hideout")))

g.add((dbr.InfestedVineyard, RDFS.subClassOf, mappin_base_class))
g.add((dbr.InfestedVineyard, RDFS.label, Literal("Infested Vineyard")))
g.add((dbr.InfestedVineyard, RDFS.subClassOf, witcher.Vineyards))

g.add((dbr.KnightErrant, RDFS.subClassOf, mappin_base_class))
g.add((dbr.KnightErrant, RDFS.label, Literal("Knight Errant")))

g.add((dbr.MutagenDismantle, RDFS.subClassOf, mappin_base_class))
g.add((dbr.MutagenDismantle, RDFS.label, Literal("Mutagen Dismantle")))

g.add((dbr.Plegmund, RDFS.subClassOf, mappin_base_class))
g.add((dbr.Plegmund, RDFS.label, Literal("Plegmund")))

g.add((dbr.SignalingStake, RDFS.subClassOf, mappin_base_class))
g.add((dbr.SignalingStake, RDFS.label, Literal("Signaling Stake")))

g.add((dbr.WineContract, RDFS.subClassOf, mappin_base_class))
g.add((dbr.WineContract, RDFS.label, Literal("Wine Contract")))


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