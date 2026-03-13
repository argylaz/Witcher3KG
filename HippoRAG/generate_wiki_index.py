import json
import igraph as ig
import re
from rdflib import Graph, URIRef, RDFS, Namespace
from tqdm import tqdm
from llama_index.core import Document, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import os

# --- CONFIG ---
RELATIONAL_KG = "../RDF/Witcher3KG_Relational.n3"
FULL_KG = "../RDF/Witcher3KG_full.ttl" # The one with the full wiki page texts
OUTPUT_DIR = "./witcher_wiki_index"
PASSAGES_FILE = os.path.join(OUTPUT_DIR, "lore_passages.jsonl")
GRAPH_FILE = os.path.join(OUTPUT_DIR, "topology.pkl")
ENTITY_MAP_FILE = os.path.join(OUTPUT_DIR, "entity_map.json")

# Namespaces
WITCHER = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")

def clean_wiki_text(text):
    """Trims long text to a manageable context window for the model"""
    # Remove HTML/XML tags and clean whitespace
    text = re.sub(r'<.*?>', '', str(text))
    text = text.replace('\r', ' ').replace('\n', ' ')
    # Limit to first 800 words to avoid token overload
    words = text.split()
    return " ".join(words[:800])

def build_wiki_index():
    print(f"[*] Loading Relational KG for Topology: {RELATIONAL_KG}...")
    rel_kg = Graph()
    rel_kg.parse(RELATIONAL_KG, format="n3")

    print(f"[*] Loading Full KG for Wiki Texts: {FULL_KG}...")
    full_kg = Graph()
    full_kg.parse(FULL_KG, format="turtle")

    all_uris = sorted(list(set(rel_kg.subjects()) | {o for o in rel_kg.objects() if isinstance(o, URIRef)}))
    uri_to_id = {str(uri): i for i, uri in enumerate(all_uris)}
    
    lore_passages = []
    nodes_for_vector = []

    print("[*] Extracting Wiki Texts and Mapping Entities...")
    for i, uri in enumerate(tqdm(all_uris)):
        # Get Label
        label = rel_kg.value(uri, RDFS.label)
        name = str(label) if label else str(uri).split('/')[-1].replace('_', ' ')
        
        # Get Full Wiki Text from the Full KG
        wiki_text = full_kg.value(uri, WITCHER.hasFullText)
        
        if wiki_text:
            text_content = clean_wiki_text(wiki_text)
        else:
            # Fallback to a triple summary if Wiki text is missing for a small node
            text_content = f"Lore for {name}. No detailed wiki entry available."

        lore_passages.append({"id": i, "name": name, "text": text_content})
        nodes_for_vector.append(Document(text=name, metadata={"uri": str(uri), "internal_id": i}))

    print("[*] Building Structural Index (Edges)...")
    edges = []
    for s, p, o in rel_kg:
        if str(s) in uri_to_id and str(o) in uri_to_id:
            edges.append((uri_to_id[str(s)], uri_to_id[str(o)]))
    
    graph = ig.Graph(n=len(all_uris), edges=edges, directed=False)
    graph = graph.simplify()
    graph.write_pickle(GRAPH_FILE)

    print("[*] Persisting Indices...")
    VectorStoreIndex.from_documents(nodes_for_vector, embed_model=embed_model).storage_context.persist(persist_dir=os.path.join(OUTPUT_DIR, "vector_index"))
    
    with open(PASSAGES_FILE, 'w', encoding='utf-8') as f:
        for p in lore_passages: f.write(json.dumps(p) + "\n")
    
    with open(ENTITY_MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump({"to_id": uri_to_id}, f)
    
    print(f"\n[!] Wiki-Enhanced Indexing Complete!")
    print(f"Index Location: {OUTPUT_DIR}")

if __name__ == "__main__":
    build_wiki_index()